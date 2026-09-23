"""
Functions for downloading specific to TJPR
"""
import re

from bs4 import BeautifulSoup, Tag
from tqdm.auto import tqdm

from juscraper.core.http import RequestFn

BASE_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
SEARCH_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"
RESULTS_PER_PAGE = 10

_PAGINATOR_SELECTOR = "#navigator .navRight"
_PAGE_NUMBER_RE = re.compile(r"\['pageNumber'\]\.value='([^']*)'")


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


def _last_page_from_paginator(paginator: Tag) -> int:
    """Lê o total de páginas do link "Última Página" de um paginador.

    Ativo, o link é ``a.arrowLastOn`` e o href em JavaScript carrega
    ``['pageNumber'].value='<total>'``. Desativado, o portal desenha a mesma
    âncora com classe ``arrowLastOff`` e sem href.
    """
    link = paginator.select_one("a.arrowLastOn")
    if link is None:
        if paginator.select_one("a.arrowLastOff") is not None:
            return 1
        raise ValueError(
            "TJPR: paginador sem o link de última página (a.arrowLastOn); "
            "o total de páginas não pode ser determinado sem estimar."
        )
    href = str(link.get("href", ""))
    match = _PAGE_NUMBER_RE.search(href)
    page = match.group(1) if match else ""
    if not re.fullmatch(r"[0-9]+", page) or int(page) < 1:
        raise ValueError(f"TJPR: link de última página sem pageNumber válido no href: {href!r}")
    return int(page)


def extract_total_pages(html: str) -> int:
    """Extrai o total de páginas da primeira página de resultados do TJPR.

    O paginador (``#navigator .navRight``) não exibe "Página X de Y" e mostra
    só uma janela de links numerados; o total vem do link "Última Página".
    O maior ``pageNumber`` da página não serve: sem o link "Última", ele é o
    fim da janela (3 na página 1), não o total. Sem paginador, ou com o
    ``.navRight`` vazio que o portal desenha quando a busca não tem
    resultados, o retorno é 1.

    Vale para a primeira página, a única que :func:`cjsg_download` lê. Nela,
    "Última" desativada (``a.arrowLastOff``) só ocorre se a página 1 for a
    última, e o retorno é 1. Essa forma foi confirmada com sample real de
    busca de página única, em que os dois paginadores trazem "Primeira",
    "Anterior", "Próxima" e "Última" desativadas. Em outra página, "Última"
    desativada daria 1 em vez do número dela. O TJPR desenha dois
    paginadores iguais, acima e abaixo da lista, e os dois precisam dar o
    mesmo total.

    Raises:
        ValueError: Paginador sem o link "Última" (ativo ou desativado),
            link sem ``pageNumber`` inteiro positivo no href ou paginadores
            com totais diferentes.
    """
    paginators = [
        paginator
        for paginator in BeautifulSoup(html, "html.parser").select(_PAGINATOR_SELECTOR)
        if paginator.find(True) is not None
    ]
    if not paginators:
        return 1
    totals = {_last_page_from_paginator(paginator) for paginator in paginators}
    if len(totals) > 1:
        raise ValueError(f"TJPR: paginadores discordam do total de páginas: {sorted(totals)}")
    return totals.pop()


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
