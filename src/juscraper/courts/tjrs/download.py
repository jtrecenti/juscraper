"""
Downloads raw files from the TJRS jurisprudence search.
"""
import math
from urllib.parse import urlencode

import requests
from tqdm import tqdm

BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
RESULTS_PER_PAGE = 10


def build_cjsg_inner_payload(
    termo: str,
    pagina_1based: int,
    *,
    classe: str | None = None,
    assunto: str | None = None,
    orgao_julgador: str | None = None,
    relator: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    tipo_processo: str | None = None,
    secao: str | None = None,
    **kwargs,
) -> dict:
    """Build the inner Solr params sent to the TJRS jurisprudence AJAX endpoint.

    Shared between the scraper and the offline capture script so both stay
    in sync with the API contract (including the 1-based ``pagina_atual``).
    """
    payload = {
        "aba": "jurisprudencia",
        "realizando_pesquisa": "1",
        "pagina_atual": str(pagina_1based),
        "start": "0",
        "q_palavra_chave": termo,
        "conteudo_busca": kwargs.get("conteudo_busca", "ementa_completa"),
        "filtroComAExpressao": kwargs.get("filtroComAExpressao", ""),
        "filtroComQualquerPalavra": kwargs.get("filtroComQualquerPalavra", ""),
        "filtroSemAsPalavras": kwargs.get("filtroSemAsPalavras", ""),
        "filtroTribunal": kwargs.get("filtroTribunal", "-1"),
        "filtroRelator": relator or "-1",
        "filtroOrgaoJulgador": orgao_julgador or "-1",
        "filtroTipoProcesso": tipo_processo or "-1",
        "filtroClasseCnj": classe or "-1",
        "assuntoCnj": assunto or "-1",
        "data_julgamento_de": data_julgamento_inicio or "",
        "data_julgamento_ate": data_julgamento_fim or "",
        "filtroNumeroProcesso": kwargs.get("filtroNumeroProcesso", ""),
        "data_publicacao_de": data_publicacao_inicio or "",
        "data_publicacao_ate": data_publicacao_fim or "",
        "facet": "on",
        "facet.sort": "index",
        "facet.limit": "index",
        "wt": "json",
        "ordem": kwargs.get("ordem", "desc"),
        "facet_orgao_julgador": "",
        "facet_origem": "",
        "facet_relator_redator": "",
        "facet_ano_julgamento": "",
        "facet_nome_classe_cnj": "",
        "facet_nome_assunto_cnj": "",
        "facet_nome_tribunal": "",
        "facet_tipo_processo": "",
        "facet_mes_ano_publicacao": "",
    }
    if secao:
        secao_map = {"civel": "C", "crime": "P"}
        valor = secao_map.get(secao.lower())
        if valor:
            payload["filtroSecao"] = valor
    return payload


def cjsg_download_manager(
    termo: str,
    paginas=None,
    classe: str | None = None,
    assunto: str | None = None,
    orgao_julgador: str | None = None,
    relator: str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    tipo_processo: str | None = None,
    secao: str | None = None,
    session: requests.Session | None = None,
    **kwargs,
) -> list:
    """
    Downloads raw files from the TJRS jurisprudence search (multiple pages).
    Returns a list of raw files (JSON).

    Args:
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        secao: 'civel', 'crime', or None.
    """
    if session is None:
        session = requests.Session()

    def _fetch_page(pagina_1based):
        payload = build_cjsg_inner_payload(
            termo,
            pagina_1based,
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
        parametros_str = urlencode(payload, doseq=True)
        data = {
            'action': 'consultas_solr_ajax',
            'metodo': 'buscar_resultados',
            'parametros': parametros_str,
        }
        resp = session.post(BASE_URL, data=data)
        resp.raise_for_status()
        return resp.json()

    if paginas is None:
        # Download all pages: fetch first to get numFound, then the rest
        first = _fetch_page(1)
        resultados = [first]
        num_found = first.get('response', {}).get('numFound', 0)
        n_pags = math.ceil(num_found / RESULTS_PER_PAGE) if num_found else 1
        if n_pags > 1:
            for pagina in tqdm(range(2, n_pags + 1), desc='Baixando páginas TJRS'):
                resultados.append(_fetch_page(pagina))
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_1based in tqdm(paginas_iter, desc='Baixando páginas TJRS'):
        resultados.append(_fetch_page(pagina_1based))
    return resultados
