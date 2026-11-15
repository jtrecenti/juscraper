"""HTTP-level helpers for the TJMG jurisprudence search."""
from __future__ import annotations

import functools
import logging
import math
import re
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import requests

from juscraper.core.exceptions import CaptchaEsgotadoError, ColetaParcialError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import paginas_no_intervalo

from .parse import TJMGBuscaSemListaError, busca_sem_lista, cjsg_parse, listas_da_busca_categorizada

logger = logging.getLogger("juscraper.tjmg")

BASE = "https://www5.tjmg.jus.br/jurisprudencia"
FORM_URL = f"{BASE}/formEspelhoAcordao.do"
SEARCH_URL = f"{BASE}/pesquisaPalavrasEspelhoAcordao.do"
CAPTCHA_IMG_URL = f"{BASE}/captcha.svl"
DWR_VALIDATE_URL = (
    f"{BASE}/dwr/call/plaincall/ValidacaoCaptchaAction.isCaptchaValid.dwr"
)

PERFIL_CJSG = "cjsg"
"""Perfil HTTP de todas as requisicoes do ``cjsg`` (formulario, captcha e busca)."""

RESULTS_PER_PAGE = 10
MAX_RESULTS = 400  # TJMG caps result lists at 400 entries.

_TOTAL_RE = re.compile(r"totalLinhas=(\d+)")
_MUITOS_RE = re.compile(r"muitos resultados\s*\(([\d.,]+)\)", re.IGNORECASE)


def _solve_captcha(
    request_fn: RequestFn,
    session: requests.Session,
    max_attempts: int = 3,
) -> bool:
    """Fetch a TJMG captcha image, decode it with txtcaptcha, validate via DWR.

    Returns True on success. The validation side-effect is stored in the
    server-side session, so subsequent search requests succeed. The local
    loop of up to ``max_attempts`` tries is a semantic retry (wrong OCR
    decoding) — distinct from the transport-level retry already centralized
    in ``request_fn`` (perfil ``"cjsg"``) for 403/429/500/502/503/504, timeouts and
    dropped connections.
    """
    try:
        import txtcaptcha
    except ImportError as exc:  # pragma: no cover - dependency check
        raise RuntimeError(
            "TJMG requires txtcaptcha to decode its image captcha. "
            "Install it with `pip install txtcaptcha`."
        ) from exc

    jsid = session.cookies.get("JSESSIONID", "")
    for attempt in range(1, max_attempts + 1):
        img_resp = request_fn(
            "GET", f"{CAPTCHA_IMG_URL}?{time.time()}", perfil=PERFIL_CJSG
        )
        img = img_resp.content
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix="tjmg_captcha_", suffix=".png", delete=False
        ) as f:
            f.write(img)
            tmp = Path(f.name)
        try:
            codes = txtcaptcha.decrypt([str(tmp)], mask="[0-9]", length=5)
        finally:
            tmp.unlink(missing_ok=True)
        code = codes[0] if isinstance(codes, list) else codes
        body = (
            "callCount=1\n"
            "page=/jurisprudencia/captcha.do\n"
            f"httpSessionId={jsid}\n"
            "scriptSessionId=juscrapertjmgsession\n"
            "c0-scriptName=ValidacaoCaptchaAction\n"
            "c0-methodName=isCaptchaValid\n"
            "c0-id=0\n"
            f"c0-param0=string:{code}\n"
            "batchId=0\n"
        )
        resp = request_fn(
            "POST",
            DWR_VALIDATE_URL,
            data=body,
            headers={"Content-Type": "text/plain"},
            perfil=PERFIL_CJSG,
        )
        if "'0','0',true" in resp.text:
            return True
        logger.warning("TJMG captcha attempt %s failed (code=%s)", attempt, code)
    return False


def _build_params(
    pesquisa: str,
    pagina: int,
    total: int,
    pesquisar_por: str,
    order_by: str,
    data_julgamento_inicial: str,
    data_julgamento_final: str,
    data_publicacao_inicial: str,
    data_publicacao_final: str,
    linhas_por_pagina: int,
) -> dict:
    offset = (pagina - 1) * linhas_por_pagina + 1
    return {
        "numeroRegistro": str(offset),
        "totalLinhas": str(total),
        "paginaNumero": str(pagina),
        "palavras": pesquisa,
        "pesquisarPor": pesquisar_por,
        "orderByData": order_by,
        "codigoOrgaoJulgador": "",
        "codigoCompostoRelator": "",
        "classe": "",
        "codigoAssunto": "",
        "dataPublicacaoInicial": data_publicacao_inicial,
        "dataPublicacaoFinal": data_publicacao_final,
        "dataJulgamentoInicial": data_julgamento_inicial,
        "dataJulgamentoFinal": data_julgamento_final,
        "siglaLegislativa": "",
        "referenciaLegislativa": (
            "Clique na lupa para pesquisar as referências cadastradas..."
        ),
        "numeroRefLegislativa": "",
        "anoRefLegislativa": "",
        "legislacao": "",
        "norma": "",
        "descNorma": "",
        "complemento_1": "",
        "listaPesquisa": "",
        "descricaoTextosLegais": "",
        "observacoes": "",
        "linhasPorPagina": str(linhas_por_pagina),
        "pesquisaPalavras": "Pesquisar",
    }


def _fetch_page(request_fn: RequestFn, params: dict) -> str:
    resp = request_fn("GET", SEARCH_URL, params=params, perfil=PERFIL_CJSG)
    resp.encoding = "iso-8859-1"
    return resp.text


def _validate_session(
    request_fn: RequestFn,
    session: requests.Session,
    max_attempts: int = 3,
) -> None:
    """Open the search form and validate the captcha in the current session.

    Usado na abertura do ``cjsg`` e de novo quando a validacao expira no meio
    da paginacao (HTTP 401), para que as duas entradas repitam a mesma
    sequencia (formulario, captcha, DWR) e a mesma mensagem de erro.

    Raises:
        CaptchaEsgotadoError: O portal recusou o captcha nas ``max_attempts``
            tentativas (motivo ``captcha_esgotado``).
    """
    request_fn("GET", FORM_URL, perfil=PERFIL_CJSG)
    if not _solve_captcha(request_fn, session, max_attempts=max_attempts):
        raise CaptchaEsgotadoError(
            f"TJMG captcha validation failed after {max_attempts} attempts."
        )


def _fetch_page_revalidating(
    request_fn: RequestFn,
    session: requests.Session,
    params: dict,
    max_revalidations: int = 2,
) -> str:
    """Fetch a result page, re-solving the captcha when the session expires.

    A validacao do captcha expira no meio da paginacao (observado em torno
    da 15a pagina): o backend passa a responder HTTP 401. Nesse caso,
    revalidamos o captcha na mesma sessao e repetimos a pagina.
    """
    for attempt in range(max_revalidations + 1):
        try:
            return _fetch_page(request_fn, params)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status != 401 or attempt == max_revalidations:
                raise
            logger.info("TJMG: sessao do captcha expirou (HTTP 401); revalidando.")
            _validate_session(request_fn, session)
    raise AssertionError("unreachable")  # pragma: no cover


def _extract_total(html: str) -> int | None:
    m = _MUITOS_RE.search(html)
    if m:
        raw = m.group(1).replace(".", "").replace(",", "")
        return int(raw)
    m = _TOTAL_RE.search(html)
    if m:
        return int(m.group(1))
    return None


def cjsg_download(
    pesquisa: str,
    paginas,
    pesquisar_por: str,
    order_by: str,
    data_julgamento_inicial: str,
    data_julgamento_final: str,
    data_publicacao_inicial: str,
    data_publicacao_final: str,
    linhas_por_pagina: int,
    sleep_time: float,
    *,
    request_fn: RequestFn,
    session: requests.Session,
) -> list:
    """Run the TJMG acórdão search and return the raw HTML of each page.

    Parameters
    ----------
    request_fn : RequestFn
        HTTP callable that handles retry + raise_for_status — em uso normal e
        ``TJMGScraper._request_with_retry`` (via ``core.http.HTTPScraper``),
        chamado com o perfil :data:`PERFIL_CJSG`, que centraliza o backoff
        exponencial para 403/429/500/502/503/504, timeout e
        conexao derrubada.
    session : requests.Session
        Compartilhada com ``request_fn`` (mesma session do
        :class:`HTTPScraper`). Precisamos do handle direto para ler o
        ``JSESSIONID`` do cookie jar e montá-lo no body DWR do captcha.
    """
    _validate_session(request_fn, session)

    def params(pagina: int, total: int, extra: dict[str, str]) -> dict:
        base = _build_params(
            pesquisa=pesquisa,
            pagina=pagina,
            total=total,
            pesquisar_por=pesquisar_por,
            order_by=order_by,
            data_julgamento_inicial=data_julgamento_inicial,
            data_julgamento_final=data_julgamento_final,
            data_publicacao_inicial=data_publicacao_inicial,
            data_publicacao_final=data_publicacao_final,
            linhas_por_pagina=linhas_por_pagina,
        )
        return {**base, **extra}

    first_html = _fetch_page(request_fn, params(1, 1, {}))
    if "muitos resultados" in first_html:
        raise ValueError(
            "TJMG returned 'muitos resultados' — refine the search "
            "(add date range or narrower terms)."
        )
    listas = _listas(first_html, params(1, 1, {}))
    results: list = []
    for posicao, (nome, extra) in enumerate(listas):
        _baixar_lista(
            results,
            functools.partial(params, extra=extra),
            first_html if nome is None else None,
            paginas,
            linhas_por_pagina,
            sleep_time,
            request_fn=request_fn,
            session=session,
            lista=nome,
            seguintes=[seguinte for seguinte, _ in listas[posicao + 1:]],
        )
    return results


def _listas(first_html: str, base: dict) -> list[tuple[str | None, dict[str, str]]]:
    """As listas a baixar: ``[(None, {})]`` na busca comum, uma por categoria na categorizada.

    Na categorizada, cada lista leva os parâmetros que o link dela acrescenta
    à busca (``excluirRepetitivos=true``, ``listaClasse=600``). A página com o
    erro do banco (``ORA-20000``) levanta :class:`TJMGBuscaSemListaError`.
    """
    categorias = listas_da_busca_categorizada(first_html)
    if categorias:
        return [
            (nome, {chave: valor for chave, valor in link.items() if chave not in base})
            for nome, link in categorias
        ]
    motivo = busca_sem_lista(first_html)
    if motivo:
        raise TJMGBuscaSemListaError(motivo)
    return [(None, {})]


def _baixar_lista(
    results: list,
    params: Callable[[int, int], dict],
    primeira: str | None,
    paginas,
    linhas_por_pagina: int,
    sleep_time: float,
    *,
    request_fn: RequestFn,
    session: requests.Session,
    lista: str | None,
    seguintes: list[str | None],
) -> None:
    """Acrescenta a ``results`` as ``paginas`` de uma lista, a partir da página 1.

    ``primeira`` é a página 1 já baixada, ou ``None`` para baixá-la aqui
    (listas da busca categorizada, nomeadas em ``lista``). A página que falha
    com outra já em ``results`` levanta :class:`ColetaParcialError`.
    """
    def baixar(pagina: int, total: int, faltando: list | None) -> str:
        try:
            return _fetch_page_revalidating(request_fn, session, params(pagina, total))
        except Exception as exc:  # noqa: BLE001 - vai para ColetaParcialError, como no auto-chunk
            if not results:
                raise
            raise _coleta_parcial(results, pagina, faltando, exc, lista, seguintes) from exc

    if primeira is None:
        time.sleep(sleep_time)
        primeira = baixar(1, 1, None if paginas is None else list(paginas))
    total = _extract_total(primeira) or 0
    if total == 0:
        logger.info("TJMG: nenhum resultado para a pesquisa.")
        results.append(primeira)
        return

    n_pags = max(1, math.ceil(total / linhas_por_pagina))
    validas = paginas_no_intervalo(paginas, n_pags, tribunal="TJMG")
    for posicao, pagina in enumerate(validas):
        if pagina == 1:
            results.append(primeira)
            continue
        time.sleep(sleep_time)
        results.append(baixar(pagina, total, validas[posicao:]))


def _coleta_parcial(
    results: list,
    pagina: int,
    faltando: list | None,
    exc: Exception,
    lista: str | None,
    seguintes: list[str | None],
) -> ColetaParcialError:
    """``ColetaParcialError`` com as paginas baixadas antes de ``pagina`` falhar.

    A pagina que falha encerra a paginacao, ao contrario do auto-chunk do
    eSAJ, que tenta as janelas seguintes: depois das tentativas do perfil
    ``"cjsg"``, o portal costuma seguir fora do ar, e as paginas seguintes
    custariam as mesmas tentativas. Por isso ``falhas`` tem um item so, e a
    mensagem lista todas as paginas que faltam (``faltando``; ``None`` quando
    faltam todas). Na busca categorizada, a mensagem nomeia a lista da pagina
    e as listas seguintes, nao baixadas.
    """
    da_lista = f" da lista {lista!r}" if lista else ""
    paginas_que_faltam = "todas as páginas" if faltando is None else f"as páginas {faltando}"
    mensagem = (
        f"TJMG cjsg: a página {pagina}{da_lista} falhou ({exc!r}), e a busca parou. "
        f"As {len(results)} página(s) baixadas antes estão, já lidas, no atributo .resultado do erro; "
        f"faltam {paginas_que_faltam}{da_lista}, que podem ser pedidas de novo com paginas=."
    )
    if seguintes:
        mensagem += f" As listas seguintes da busca categorizada, {seguintes}, também não foram baixadas."
    return ColetaParcialError(mensagem, resultado=cjsg_parse(results), falhas=[(None, None, exc)])
