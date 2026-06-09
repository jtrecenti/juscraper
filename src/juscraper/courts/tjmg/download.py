"""HTTP-level helpers for the TJMG jurisprudence search."""
from __future__ import annotations

import logging
import math
import re
import tempfile
import time
from pathlib import Path

import requests

from juscraper.core.http import RequestFn

logger = logging.getLogger("juscraper.tjmg")

BASE = "https://www5.tjmg.jus.br/jurisprudencia"
FORM_URL = f"{BASE}/formEspelhoAcordao.do"
SEARCH_URL = f"{BASE}/pesquisaPalavrasEspelhoAcordao.do"
CAPTCHA_IMG_URL = f"{BASE}/captcha.svl"
DWR_VALIDATE_URL = (
    f"{BASE}/dwr/call/plaincall/ValidacaoCaptchaAction.isCaptchaValid.dwr"
)

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
    in ``request_fn`` for transient 429/5xx.
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
            "GET", f"{CAPTCHA_IMG_URL}?{time.time()}", timeout=60
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
            timeout=60,
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
    resp = request_fn("GET", SEARCH_URL, params=params, timeout=120)
    resp.encoding = "iso-8859-1"
    return resp.text


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
        centralizando backoff exponencial para 429/5xx.
    session : requests.Session
        Compartilhada com ``request_fn`` (mesma session do
        :class:`HTTPScraper`). Precisamos do handle direto para ler o
        ``JSESSIONID`` do cookie jar e montá-lo no body DWR do captcha.
    """
    request_fn("GET", FORM_URL, timeout=60)
    if not _solve_captcha(request_fn, session):
        raise RuntimeError(
            "TJMG captcha validation failed after 3 attempts."
        )

    first_params = _build_params(
        pesquisa=pesquisa,
        pagina=1,
        total=1,
        pesquisar_por=pesquisar_por,
        order_by=order_by,
        data_julgamento_inicial=data_julgamento_inicial,
        data_julgamento_final=data_julgamento_final,
        data_publicacao_inicial=data_publicacao_inicial,
        data_publicacao_final=data_publicacao_final,
        linhas_por_pagina=linhas_por_pagina,
    )
    first_html = _fetch_page(request_fn, first_params)
    if "muitos resultados" in first_html:
        raise ValueError(
            "TJMG returned 'muitos resultados' — refine the search "
            "(add date range or narrower terms)."
        )
    total = _extract_total(first_html) or 0
    if total == 0:
        logger.info("TJMG: nenhum resultado para a pesquisa.")
        return [first_html]

    n_pags = max(1, math.ceil(total / linhas_por_pagina))

    if paginas is None:
        paginas = range(1, n_pags + 1)

    results: list = []
    for pagina in paginas:
        if pagina < 1 or pagina > n_pags:
            logger.warning(
                "TJMG: página %s fora do intervalo 1-%s", pagina, n_pags
            )
            continue
        if pagina == 1:
            results.append(first_html)
            continue
        time.sleep(sleep_time)
        params = _build_params(
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
        results.append(_fetch_page(request_fn, params))
    return results
