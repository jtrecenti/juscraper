"""Downloads raw results from the TJRS jurisprudence search.

The TJRS frontend was rewritten on top of WordPress. The new public
endpoint is ``/novo/wp-admin/admin-ajax.php?action=busca_jurisprudencia``
(GET), which returns a JSON envelope containing pre-rendered HTML. The
old Solr-backed ``/buscas/jurisprudencia/ajax.php`` remains live but
now intermittently 503s on the internal cluster (``no servers hosting
shard: shard6``), so we always prefer the new endpoint.
"""
import math

import requests
from tqdm import tqdm

BASE_URL = "https://www.tjrs.jus.br/novo/wp-admin/admin-ajax.php"
REFERER = (
    "https://www.tjrs.jus.br/novo/busca-jurisprudencia/"
    "?palavra-chave=&conteudo_busca=ementa_completa"
)
RESULTS_PER_PAGE = 10


def _build_params(
    termo: str,
    pagina_1based: int,
    classe: str = None,
    assunto: str = None,
    orgao_julgador: str = None,
    relator: str = None,
    data_julgamento_inicio: str = None,
    data_julgamento_fim: str = None,
    data_publicacao_inicio: str = None,
    data_publicacao_fim: str = None,
    tipo_processo: str = None,
    secao: str = None,
    **kwargs,
) -> dict:
    """Build query params matching what the WordPress frontend sends."""
    secao_civel = "false"
    secao_crime = "false"
    if secao:
        s = secao.lower()
        if s == "civel":
            secao_civel = "true"
        elif s == "crime":
            secao_crime = "true"
    return {
        "action": "busca_jurisprudencia",
        "palavra_chave": termo or "",
        "tipo_consulta": kwargs.get("tipo_consulta", "ementa"),
        "filtroComAExpressao": kwargs.get("filtroComAExpressao", ""),
        "filtroComQualquerPalavra": kwargs.get("filtroComQualquerPalavra", ""),
        "filtroSemAsPalavras": kwargs.get("filtroSemAsPalavras", ""),
        "filtroTribunal": kwargs.get("filtroTribunal", ""),
        "filtroRelator": relator or "",
        "filtroOrgaoJulgador": orgao_julgador or "",
        "filtroTipoProcesso": tipo_processo or "",
        "filtroClasseCnj": classe or "",
        "filtroAssuntoCnj": assunto or "",
        "data_julgamento_de": data_julgamento_inicio or "",
        "data_julgamento_ate": data_julgamento_fim or "",
        "filtroNumeroProcesso": kwargs.get("filtroNumeroProcesso", ""),
        "data_publicacao_de": data_publicacao_inicio or "",
        "data_publicacao_ate": data_publicacao_fim or "",
        "filtroSecaoCivel": secao_civel,
        "filtroSecaoCrime": secao_crime,
        "filtroacordao": kwargs.get("filtroacordao", "false"),
        "filtroMonocratica": kwargs.get("filtroMonocratica", "false"),
        "filtroAdmissibilidade": kwargs.get("filtroAdmissibilidade", "false"),
        "filtroDuvida": kwargs.get("filtroDuvida", "false"),
        "orgao_julgador": "",
        "comarca_origem": "",
        "redator": "",
        "ano_julgamento": "",
        "classe_cnj": "",
        "assunto_cnj": "",
        "tribunal": "",
        "tipo_processo": "",
        "data_publicacao": "",
        "num_page": str(pagina_1based),
    }


def cjsg_download_manager(
    termo: str,
    paginas=None,
    classe: str = None,
    assunto: str = None,
    orgao_julgador: str = None,
    relator: str = None,
    data_julgamento_inicio: str = None,
    data_julgamento_fim: str = None,
    data_publicacao_inicio: str = None,
    data_publicacao_fim: str = None,
    tipo_processo: str = None,
    secao: str = None,
    session: requests.Session = None,
    **kwargs,
) -> list:
    """Download raw JSON pages from the TJRS WordPress endpoint.

    Each element is the parsed JSON response; ``.data.html`` contains
    the result list rendered as HTML (parsed downstream by ``cjsg_parse``).
    """
    if session is None:
        session = requests.Session()
    session.headers.setdefault(
        "User-Agent",
        "Mozilla/5.0 (juscraper/0.1; +https://github.com/jtrecenti/juscraper)",
    )
    session.headers.setdefault("Referer", REFERER)
    session.headers.setdefault("Accept", "*/*")

    def _fetch_page(pagina_1based: int) -> dict:
        params = _build_params(
            termo=termo,
            pagina_1based=pagina_1based,
            classe=classe,
            assunto=assunto,
            orgao_julgador=orgao_julgador,
            relator=relator,
            data_julgamento_inicio=data_julgamento_inicio,
            data_julgamento_fim=data_julgamento_fim,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            tipo_processo=tipo_processo,
            secao=secao,
            **kwargs,
        )
        resp = session.get(BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    if paginas is None:
        first = _fetch_page(1)
        resultados = [first]
        total = (first.get("data") or {}).get("total", 0) or 0
        n_pags = math.ceil(total / RESULTS_PER_PAGE) if total else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc="Baixando paginas TJRS"):
                resultados.append(_fetch_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc="Baixando paginas TJRS"):
        resultados.append(_fetch_page(pagina_1based))
    return resultados
