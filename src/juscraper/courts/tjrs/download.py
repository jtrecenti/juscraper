"""Downloads raw files from the TJRS jurisprudence search."""
from urllib.parse import urlencode

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import Paginas, baixar_paginas_pedidas, resolve_total_pages

from .parse import TJRSBuscaError, cjsg_parse_manager, exigir_resultados

# ``TJRSBuscaError`` mora em ``parse``; este módulo é o caminho documentado dele.
__all__ = [
    "BASE_URL",
    "PERFIL_CJSG",
    "RESULTS_PER_PAGE",
    "TJRSBuscaError",
    "build_cjsg_inner_payload",
    "cjsg_download_manager",
]

BASE_URL = "https://www.tjrs.jus.br/buscas/jurisprudencia/ajax.php"
RESULTS_PER_PAGE = 10

#: Nome do perfil HTTP da busca de jurisprudência. O client declara a política
#: com a mesma chave em ``TJRSScraper.perfis_http``.
PERFIL_CJSG = "cjsg"


def build_cjsg_inner_payload(
    termo: str,
    pagina_1based: int,
    *,
    classe: int | str | None = None,
    assunto: int | str | None = None,
    orgao_julgador: int | str | None = None,
    relator: int | str | None = None,
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
        # O formulário do site tem uma caixa por seção; o backend ignora
        # ``filtroSecao``. Validada em ``InputCJSGTJRS``: valor fora do mapa falha.
        campo = {"civel": "filtroSecaoCivel", "crime": "filtroSecaoCrime"}[secao]
        payload[campo] = secao
    return payload


def cjsg_download_manager(
    termo: str,
    paginas: Paginas | None = None,
    *,
    request_fn: RequestFn,
    classe: int | str | None = None,
    assunto: int | str | None = None,
    orgao_julgador: int | str | None = None,
    relator: int | str | None = None,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    tipo_processo: str | None = None,
    secao: str | None = None,
    sleep_time: float = 1.0,
    **kwargs,
) -> list:
    """
    Downloads raw files from the TJRS jurisprudence search (multiple pages).
    Returns a list of raw files (JSON).

    Args:
        sleep_time: Pausa, em segundos, antes de cada página depois da primeira;
            o client passa ``self.sleep_time``.
        paginas: Pages to download (1-based).
            None: downloads all available pages.
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJRSScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx. Recebe ``perfil=PERFIL_CJSG`` em toda requisição.
        secao: 'civel', 'crime', or None.

    Raises:
        TJRSBuscaError: Erro do Solr na primeira página pedida.
        ColetaParcialError: Falha numa página seguinte (erro do Solr, rede
            depois das tentativas); ``.resultado`` traz as páginas
            anteriores, já lidas, em DataFrame.
    """
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
        resp = request_fn("POST", BASE_URL, data=data, perfil=PERFIL_CJSG)
        return exigir_resultados(resp.json())

    def _n_pags(data):
        num_found = data.get('response', {}).get('numFound', 0)
        return resolve_total_pages(num_found, resultados_por_pagina=RESULTS_PER_PAGE, tribunal="TJRS")

    # Vale para toda falha da página: rede depois das tentativas, corpo que não
    # é JSON e o erro do Solr.
    return baixar_paginas_pedidas(
        paginas, _fetch_page, _n_pags, tribunal="TJRS", sleep_time=sleep_time, ler_parcial=cjsg_parse_manager
    )
