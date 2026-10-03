"""
Functions for downloading specific to TJPR
"""
import re

from bs4 import BeautifulSoup
from tqdm.auto import tqdm

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import extract_count_with_cascade, parse_page_number, resolve_total_pages

BASE_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
SEARCH_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"
# O portal devolve 50 linhas por página qualquer que seja o ``pageSize``
# enviado, e usa o ``pageSize`` só para desenhar o rótulo "exibindo de X até
# Y" e o link "Última Página". Com 10, o link apontava 5 vezes mais páginas
# do que existem, e as excedentes voltavam vazias (sondagem ao vivo de
# 2026-10, "comodato": 4795 registros, link 480, página 97 vazia).
RESULTS_PER_PAGE = 50

_PAGE_NUMBER_RE = re.compile(r"\['pageNumber'\]\.value='([^']*)'")
# Cascata da contagem: o rótulo "394770 registro(s) encontrado(s)" fica em
# ``#navigator .navLeft``; se o contêiner mudar, a cascata cai no HTML bruto,
# onde a expressão "registro(s) encontrado(s)" continua específica.
_COUNT_SELECTORS = ("#navigator .navLeft",)
_COUNT_PATTERNS = (re.compile(r"([\d.]+)\s*registro\(s\)\s*encontrado", re.IGNORECASE),)


def populate_session(request_fn: RequestFn, home_url: str) -> None:
    """Hit the TJPR home so ``JSESSIONID`` lands in the session cookie jar.

    Side-effect only — the cookie is read implicitly by subsequent requests
    that share the same ``requests.Session`` (via ``request_fn`` bound to
    :class:`HTTPScraper.session`). The portal also embeds a
    ``tjpr.url.crypto`` token in the home HTML, but it is not consumed by
    any current code path; keeping it would be dead state.

    ``request_fn`` (em uso normal ``HTTPScraper._request_with_retry``) ja
    chama ``raise_for_status()`` para 4xx nao-retryable e levanta
    ``RetryExhaustedError`` em 5xx esgotado, entao a falha do GET inicial
    se propaga sem precisar de checagem extra.
    """
    request_fn("GET", home_url)


def get_ementa_completa(
    request_fn: RequestFn,
    id_processo: str,
    criterio: str,
) -> str:
    """Fetch the full minute (``actionType=exibirTextoCompleto``) for one decision.

    Headers replicate the portal's XHR (``x-prototype-version``,
    ``x-requested-with``). ``JSESSIONID`` rides on the session cookie jar
    populated by :func:`populate_session`.
    """
    url = (
        f"{SEARCH_URL}?actionType=exibirTextoCompleto"
        f"&idProcesso={id_processo}&criterio={criterio}"
    )
    headers = {
        'accept': 'text/javascript, text/html, application/xml, text/xml, */*',
        'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'referer': f"{SEARCH_URL}?actionType=pesquisar",
        'x-prototype-version': '1.5.1.1',
        'x-requested-with': 'XMLHttpRequest',
    }
    resp = request_fn("GET", url, headers=headers)
    text: str = BeautifulSoup(resp.text, 'html.parser').get_text("\n", strip=True)
    return text


def build_cjsg_form_body(
    pesquisa: str,
    page: int = 1,
    data_julgamento_inicio: str = "",
    data_julgamento_fim: str = "",
    data_publicacao_inicio: str = "",
    data_publicacao_fim: str = "",
) -> dict[str, str]:
    """Build the form-encoded body for the TJPR CJSG search endpoint.

    All values are returned as strings so that
    :func:`responses.matchers.urlencoded_params_matcher` can be used with
    ``allow_blank=True`` to assert the full payload in contract tests.
    """
    return {
        'usuarioCienteSegredoJustica': 'false',
        'segredoJustica': 'pesquisar com',
        'id': '',
        'chave': '',
        'dataJulgamentoInicio': data_julgamento_inicio,
        'dataJulgamentoFim': data_julgamento_fim,
        'dataPublicacaoInicio': data_publicacao_inicio,
        'dataPublicacaoFim': data_publicacao_fim,
        'processo': '',
        'acordao': '',
        'idComarca': '',
        'idRelator': '',
        'idOrgaoJulgador': '',
        'idClasseProcessual': '',
        'idAssunto': '',
        'pageVoltar': str(page - 1),
        'idLocalPesquisa': '1',
        'ambito': '-1',
        'descricaoAssunto': '',
        'descricaoClasseProcessual': '',
        'nomeComarca': '',
        'nomeOrgaoJulgador': '',
        'nomeRelator': '',
        'idTipoDecisaoAcordao': '',
        'idTipoDecisaoMonocratica': '',
        'idTipoDecisaoDuvidaCompetencia': '',
        'criterioPesquisa': pesquisa,
        'pesquisaLivre': '',
        'pageSize': str(RESULTS_PER_PAGE),
        'pageNumber': str(page),
        'sortColumn': 'processo_sDataJulgamento',
        'sortOrder': 'DESC',
        'page': str(page - 1),
        'iniciar': 'Pesquisar',
    }


def _last_page_links(soup: BeautifulSoup) -> set[int]:
    """Lê os totais dos links "Última Página" da página inteira.

    Ativo, o link é ``a.arrowLastOn`` e o href em JavaScript carrega
    ``['pageNumber'].value='<total>'``. Desativado, o portal desenha a mesma
    âncora com classe ``arrowLastOff`` e sem href, o que na primeira página
    quer dizer total 1. A busca cobre a página inteira, e não só o
    ``#navigator .navRight``, para que um contêiner renomeado não esconda o
    link da conferência.
    """
    totais = set()
    for link in soup.select("a.arrowLastOn"):
        href = str(link.get("href", ""))
        encontrado = _PAGE_NUMBER_RE.search(href)
        totais.add(parse_page_number(
            encontrado.group(1) if encontrado else "",
            tribunal="TJPR",
            origem=f"link de última página {href!r}",
        ))
    if soup.select_one("a.arrowLastOff") is not None:
        totais.add(1)
    return totais


def extract_total_pages(html: str) -> int:
    """Extrai o total de páginas da primeira página de resultados do TJPR.

    O total sai da contagem "N registro(s) encontrado(s)" dividida por
    ``RESULTS_PER_PAGE``, e os links "Última Página" (ativos e desativados)
    são conferidos contra ele por
    :func:`~juscraper.utils.pagination.resolve_total_pages`. O paginador não
    exibe "Página X de Y", e o maior ``pageNumber`` visível é o fim da janela
    de links (3 na página 1), não o total. Vale para a primeira página, a
    única que :func:`cjsg_download` lê: na última, "Última" vem desativada.

    Raises:
        ValueError: Nos casos de :func:`~juscraper.utils.pagination.resolve_total_pages`
            e de :func:`~juscraper.utils.pagination.parse_page_number`.
    """
    n_resultados = extract_count_with_cascade(
        html,
        css_selectors=_COUNT_SELECTORS,
        regex_patterns=_COUNT_PATTERNS,
    )
    return resolve_total_pages(
        n_resultados,
        resultados_por_pagina=RESULTS_PER_PAGE,
        totais_links=_last_page_links(BeautifulSoup(html, "html.parser")),
        tribunal="TJPR",
    )


def cjsg_download(
    home_url: str,
    pesquisa: str,
    paginas=None,
    data_julgamento_inicio=None,
    data_julgamento_fim=None,
    data_publicacao_inicio=None,
    data_publicacao_fim=None,
    *,
    request_fn: RequestFn,
) -> list:
    """
    Downloads raw results from the TJPR 'jurisprudence search' (multiple pages).
    Returns a list of HTMLs (one per page).
    """
    populate_session(request_fn, home_url)
    url = f"{SEARCH_URL}?actionType=pesquisar"
    headers = {
        'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://portal.tjpr.jus.br',
        'pragma': 'no-cache',
        'referer': url,
    }

    def _fetch_page(pagina_atual):
        data = build_cjsg_form_body(
            pesquisa=pesquisa,
            page=pagina_atual,
            data_julgamento_inicio=data_julgamento_inicio or '',
            data_julgamento_fim=data_julgamento_fim or '',
            data_publicacao_inicio=data_publicacao_inicio or '',
            data_publicacao_fim=data_publicacao_fim or '',
        )
        resp = request_fn("POST", url, data=data, headers=headers)
        return resp.text

    if paginas is None:
        # Download all: fetch first page, extract total, then fetch the rest
        first_html = _fetch_page(1)
        n_pags = extract_total_pages(first_html)
        resultados = [first_html]
        if n_pags > 1:
            for pagina_atual in tqdm(range(2, n_pags + 1), desc='Baixando páginas TJPR'):
                # laco de I/O (rede por iteracao sob tqdm): comprehension esconderia o efeito
                resultados.append(_fetch_page(pagina_atual))  # noqa: PERF401
        return resultados

    paginas_iter = list(paginas)
    resultados = []
    for pagina_atual in tqdm(paginas_iter, desc='Baixando páginas TJPR'):
        resultados.append(_fetch_page(pagina_atual))
    return resultados
