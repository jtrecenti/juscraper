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
import os
import re
import tempfile
from typing import Optional

import requests

logger = logging.getLogger("juscraper.trf6.download")

BASE_URL = "https://eproc1g.trf6.jus.br/eproc/"
GET_PATH = "externo_controlador.php?acao=processo_consulta_publica"
POST_PATH = (
    "externo_controlador.php?acao=processo_consulta_publica"
    "&acao_origem=principal&acao_retorno=processo_consulta_publica"
)

BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    ),
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

# eproc echoes captcha validation errors in a hidden textarea that JS would
# normally pop as an alert. We sniff this on a 200 response to decide whether
# to retry with a fresh captcha.
_CAPTCHA_ERROR_RE = re.compile(r"captcha\)\s*incorreto", re.IGNORECASE)


def fetch_form(session: requests.Session, timeout: float = 30.0) -> str:
    """``GET`` the consulta form. Returns latin-1 text with captcha embedded."""
    resp = session.get(BASE_URL + GET_PATH, timeout=timeout)
    resp.raise_for_status()
    return resp.content.decode("latin-1")


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
        return txtcaptcha.decrypt([tmp_path])[0]
    finally:
        os.unlink(tmp_path)


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
    timeout: float = 30.0,
) -> str:
    """``POST`` the search payload and return the response as latin-1 text."""
    resp = session.post(
        BASE_URL + POST_PATH,
        data=payload,
        timeout=timeout,
        headers={"Referer": BASE_URL + GET_PATH},
    )
    resp.raise_for_status()
    return resp.content.decode("latin-1")


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


def fetch_detail(
    session: requests.Session,
    numero_processo: str,
    *,
    max_captcha_attempts: int = 3,
    timeout: float = 30.0,
) -> Optional[str]:
    """Run the full captcha-solving lookup for one CNJ.

    Returns the detail HTML (latin-1 decoded text) on success, or ``None``
    when the CNJ matches no process. Raises :class:`RuntimeError` if the
    captcha solver keeps failing past ``max_captcha_attempts`` retries.
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
        # No captcha error and no detail → the CNJ doesn't match anything
        # the public consultation can return (sigilo, archived, invalid).
        return None

    raise RuntimeError(
        f"TRF6: captcha solver failed {max_captcha_attempts} times for "
        f"{numero_processo!r} (last attempt: {last_err})"
    )
