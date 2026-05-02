"""HTTP-level helpers for the TJMG jurisprudence search."""
from __future__ import annotations

import logging
import math
import re
import time
from pathlib import Path

import requests

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


def _solve_captcha(session: requests.Session, max_attempts: int = 3) -> bool:
    """Fetch a TJMG captcha image, decode it with txtcaptcha, validate via DWR.

    Returns True on success. The validation side-effect is stored in the
    server-side session, so subsequent search requests succeed.
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
        img = session.get(
            f"{CAPTCHA_IMG_URL}?{time.time()}", timeout=60
        ).content
        tmp = Path(f"/tmp/tjmg_captcha_{int(time.time()*1000)}.png")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(img)
        try:
            codes = txtcaptcha.decrypt([str(tmp)], mask="[0-9]", length=5)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
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
        resp = session.post(
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


def _fetch_page(session: requests.Session, params: dict) -> str:
    resp = session.get(SEARCH_URL, params=params, timeout=120)
    resp.raise_for_status()
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
    session: requests.Session,
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
) -> list:
    """Run the TJMG acórdão search and return the raw HTML of each page."""
    session.get(FORM_URL, timeout=60)
    if not _solve_captcha(session):
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
    first_html = _fetch_page(session, first_params)
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
        results.append(_fetch_page(session, params))
    return results
