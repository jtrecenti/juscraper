"""HTTP layer for the TRF6 eproc public-process consultation.

A single ``cpopg`` lookup is two requests plus captcha solving:

1. ``GET BASE_URL + acao=processo_consulta_publica`` — primes the session
   (``PHPSESSID`` + ``TS01...`` cookies) and returns the form HTML, which
   carries the captcha image embedded as ``data:image/png;base64,...``
   inline.
2. Solve the captcha with :func:`solve_captcha` (delegates to
   :mod:`txtcaptcha`).
3. ``POST <same controller URL with action params>`` with the search
   payload — when the CNJ matches a single process, the response is the
   detail page directly (``Detalhes do Processo`` in the title); when the
   CNJ doesn't match, the response is the form again with no error; when
   the captcha was wrong, the response is the form with a hidden
   ``txaInfraValidacao`` textarea carrying ``"Código da imagem (captcha)
   incorreto."`` which the caller uses to retry.

Detail and form pages are both served as **latin-1** (``iso-8859-1`` per
the meta charset).
"""
from __future__ import annotations

import base64
import logging
import re
import tempfile
from pathlib import Path

import requests

from juscraper import __version__

from ...core.exceptions import BotChallengeBlockedError, CaptchaEsgotadoError

logger = logging.getLogger("juscraper.trf6.download")

BASE_URL = "https://eproc1g.trf6.jus.br/eproc/"
GET_PATH = "externo_controlador.php?acao=processo_consulta_publica"
POST_PATH = (
    "externo_controlador.php?acao=processo_consulta_publica"
    "&acao_origem=principal&acao_retorno=processo_consulta_publica"
)

# User agent da biblioteca, não de navegador: em 15/11/2026, o bot manager F5
# (TSPD) do portal servia um desafio JavaScript no lugar do formulário a todo
# user agent ``Mozilla/...`` (Chrome, Firefox), e o formulário com o captcha a
# ``juscraper/...`` e ao padrão do ``requests``.
HEADERS: dict[str, str] = {
    "User-Agent": f"juscraper/{__version__} (https://github.com/jtrecenti/juscraper)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# The captcha image is embedded inline in the form HTML as a base64 PNG
# under ``<label id="lblInfraCaptcha"><img src="data:image/png;base64,...">``.
# No separate fetch needed — the bytes travel with the form.
_CAPTCHA_RE = re.compile(
    r'id="lblInfraCaptcha"[^>]*>\s*<img\s+src="data:image/png;base64,([^"]+)"',
    re.DOTALL,
)

# Página de desafio do F5 (TSPD), servida com HTTP 200 no lugar do formulário.
_MARCADORES_DESAFIO_F5 = (b"/TSPD/", b'window["bobcmn"]')


class DesafioF5Error(BotChallengeBlockedError):
    """O bot manager F5 do TRF6 serviu, com HTTP 200, um desafio JavaScript no lugar da página.

    Tratado como os demais bloqueios em :meth:`~juscraper.courts.trf6.client.TRF6Scraper.cpopg`.
    """

    def __init__(self, url: str) -> None:
        """Guarda ``url``, com a mensagem do desafio do F5 no lugar da do 403."""
        super().__init__(
            "TRF6",
            url,
            bot_manager="F5",
            mensagem=(
                f"O bot manager (F5) do TRF6 serviu um desafio JavaScript em {url} no lugar da "
                "consulta pública. O desafio sai para user agents de navegador: confira se a sessão "
                "não recebeu um User-Agent desses, ou aguarde alguns minutos antes de tentar de novo."
            ),
        )


# eproc echoes captcha validation errors in a hidden textarea that JS would
# normally pop as an alert. We sniff this on a 200 response to decide whether
# to retry with a fresh captcha.
_CAPTCHA_ERROR_RE = re.compile(r"captcha\)\s*incorreto", re.IGNORECASE)


def _texto(resp: requests.Response) -> str:
    """Corpo latin-1 de ``resp``; levanta no status de erro e no desafio do F5."""
    resp.raise_for_status()
    if all(marcador in resp.content for marcador in _MARCADORES_DESAFIO_F5):
        raise DesafioF5Error(resp.url)
    return resp.content.decode("latin-1")


def fetch_form(session: requests.Session, timeout: float | tuple[float, float] = 30.0) -> str:
    """``GET`` the consulta form. Returns latin-1 text with captcha embedded.

    Raises:
        DesafioF5Error: O portal serviu o desafio do F5 no lugar do formulário.
    """
    return _texto(session.get(BASE_URL + GET_PATH, timeout=timeout))


def extract_captcha_b64(form_html: str) -> str:
    """Pull the base64-encoded PNG of the captcha out of the form HTML."""
    m = _CAPTCHA_RE.search(form_html)
    if not m:
        raise RuntimeError("TRF6: could not locate captcha image in form HTML")
    return m.group(1)


def solve_captcha(captcha_b64: str) -> str:
    """Decode the captcha PNG and run it through ``txtcaptcha.decrypt``.

    Imports ``txtcaptcha`` lazily so it stays an optional dependency: users
    who never call :class:`TRF6Scraper` don't pay the import cost (and
    don't need the package installed).
    """
    try:
        import txtcaptcha
    except ImportError as exc:
        raise ImportError(
            "TRF6 requires the optional `txtcaptcha` package "
            "(`uv pip install txtcaptcha`)."
        ) from exc

    img_bytes = base64.b64decode(captcha_b64)
    # ``txtcaptcha.decrypt`` accepts a path; write the PNG to a temp file.
    with tempfile.NamedTemporaryFile(
        suffix=".png", delete=False
    ) as tmp:
        tmp.write(img_bytes)
        tmp_path = tmp.name
    try:
        return str(txtcaptcha.decrypt([tmp_path])[0])
    finally:
        Path(tmp_path).unlink()


def build_search_payload(numero_processo: str, captcha_text: str) -> dict[str, str]:
    """Build the urlencoded body for a single-CNJ consultation.

    All filter fields except the process number and the captcha are submitted
    empty — that's how the eproc form posts when the user fills only the
    process number, and the backend tolerates the empty values as long as
    the corresponding control fields (radio/select) are present.
    """
    return {
        "hdnInfraTipoPagina": "1",
        "txtNumProcesso": numero_processo,
        "txtNumChave": "",
        "txtNumChaveDocumento": "",
        "txtStrParte": "",
        "chkFonetica": "S",
        "rdoTipo": "CPF",
        "txtCpfCnpj": "",
        "txtStrOAB": "",
        "txtInfraCaptcha": captcha_text,
        "hdnInfraCaptcha": "0",
        "hdnInfraSelecoes": "Infra",
        "sbmNovo": "Consultar",
    }


def submit_search(
    session: requests.Session,
    payload: dict[str, str],
    timeout: float | tuple[float, float] = 30.0,
) -> str:
    """``POST`` the search payload and return the response as latin-1 text.

    Raises:
        DesafioF5Error: O portal serviu o desafio do F5 no lugar da resposta.
    """
    return _texto(
        session.post(
            BASE_URL + POST_PATH,
            data=payload,
            timeout=timeout,
            headers={"Referer": BASE_URL + GET_PATH},
        )
    )


def is_captcha_error(response_html: str) -> bool:
    """``True`` when the response indicates the captcha was wrong."""
    return bool(_CAPTCHA_ERROR_RE.search(response_html))


def is_detail_page(response_html: str) -> bool:
    """``True`` when the response is the process detail page (CNJ matched)."""
    # The detail page reuses the form layout but adds the "Detalhes do
    # Processo" title and a "Capa do Processo" fieldset; both must be
    # present to distinguish it from the form being re-served.
    return (
        "Detalhes do Processo" in response_html
        and "Capa do Processo" in response_html
    )


def is_search_form(response_html: str) -> bool:
    """``True`` when the response is the search form re-served (CNJ not matched).

    O campo de busca ``txtNumProcesso`` só existe como ``<input>`` no
    formulário; no detalhe, ``txtNumProcesso`` é o ``id`` do ``<dd>`` da capa.
    """
    return 'name="txtNumProcesso"' in response_html


def fetch_detail(
    session: requests.Session,
    numero_processo: str,
    *,
    max_captcha_attempts: int = 3,
    timeout: float | tuple[float, float] = 30.0,
) -> str | None:
    """Run the full captcha-solving lookup for one CNJ.

    Returns the detail HTML (latin-1 decoded text) on success, or ``None``
    when the CNJ matches no process (the form is re-served). Levanta
    :class:`~juscraper.core.exceptions.CaptchaEsgotadoError` quando o
    captcha é recusado nas ``max_captcha_attempts`` tentativas,
    :class:`RuntimeError` quando a resposta não é o detalhe nem o
    formulário, e :class:`DesafioF5Error` quando o portal serve o desafio do
    F5.
    Each retry fetches a fresh captcha — the captcha is bound to the
    session's ``PHPSESSID`` cookie, so re-using a stale image silently
    fails server-side validation.
    """
    last_err: str | None = None
    for attempt in range(1, max_captcha_attempts + 1):
        form_html = fetch_form(session, timeout=timeout)
        captcha_b64 = extract_captcha_b64(form_html)
        captcha_text = solve_captcha(captcha_b64)
        payload = build_search_payload(numero_processo, captcha_text)
        response = submit_search(session, payload, timeout=timeout)

        if is_detail_page(response):
            return response
        if is_captcha_error(response):
            last_err = f"captcha {captcha_text!r} rejected"
            logger.debug(
                "TRF6 attempt %d for %s: %s", attempt, numero_processo, last_err
            )
            continue
        # No captcha error and no detail, but the form → the CNJ doesn't match
        # anything the public consultation can return (sigilo, archived, invalid).
        if is_search_form(response):
            return None
        raise RuntimeError(
            f"TRF6: a busca de {numero_processo!r} devolveu uma página que não é "
            "o detalhe do processo nem o formulário da consulta"
        )

    raise CaptchaEsgotadoError(
        f"TRF6: captcha solver failed {max_captcha_attempts} times for "
        f"{numero_processo!r} (last attempt: {last_err})"
    )
