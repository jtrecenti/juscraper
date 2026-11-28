"""
Functions for downloading specific to TJPR
"""
import functools
import re
from collections.abc import Callable

import pandas as pd
from bs4 import BeautifulSoup

from juscraper.core.exceptions import HTTPSemanticError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import (
    Paginas,
    baixar_paginas_pedidas,
    extract_count_with_cascade,
    menor_pagina,
    mensagem_de_coleta_parcial,
    parse_page_number,
    resolve_total_pages,
)

BASE_URL = "https://portal.tjpr.jus.br/jurisprudencia/"
SEARCH_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/pesquisa.do"
# O "Leia mais.." chama ``insereTextoCompleto`` (linhas do TJ) ou
# ``insereTextoCompletoCidh`` (linhas da Corte IDH) em ``js/jurisprudencia.js``,
# e os dois buscam o texto neste endpoint. O ``actionType=exibirTextoCompleto``
# em ``pesquisa.do`` devolve a página do portal com o menu da intranet.
VISUALIZAR_URL = "https://portal.tjpr.jus.br/jurisprudencia/publico/visualizarDecisao.do"
# O portal devolve 50 linhas por página qualquer que seja o ``pageSize``
# enviado, e usa o ``pageSize`` só para desenhar o rótulo "exibindo de X até
# Y" e o link "Última Página". Com 10, o link apontava 5 vezes mais páginas
# do que existem, e as excedentes voltavam vazias (sondagem ao vivo de
# 2026-10, "comodato": 4795 registros, link 480, página 97 vazia).
#
# As 50 linhas somam duas fontes, a jurisprudência do TJ e os registros da
# Corte IDH, e a contagem de ``.navLeft`` é a soma das duas (410507 + 107 =
# 410614 no sample de várias páginas). Nos samples, cada página traz até 10
# registros da Corte IDH e o TJ completa as 50: 40 + 10 nas páginas 1 e 2, e
# 43 + 7 num sample anterior, de busca com só 7 registros da Corte IDH.
# Depois que a Corte IDH acaba, o TJ continua do registro em que parou, e por
# isso ``ceil(N / 50)`` cobre a busca inteira. Sondagem ao vivo de 2026-10,
# "dano moral" (411844 do TJ + 107 da Corte IDH): página 11 com TJ 401 a 443
# e Corte IDH 101 a 107, página 12 com TJ 444 a 493, página 8240 com só o
# último registro e página 8241 vazia. Se o portal mudar essa divisão, o
# sintoma é a última página calculada vir cheia. Por padrão o parser descarta
# as linhas da Corte IDH (``parse._parse_row``), então a página rende menos de 50.
RESULTS_PER_PAGE = 50

_PAGE_NUMBER_RE = re.compile(r"\['pageNumber'\]\.value='([^']*)'")
# Cascata da contagem: o rótulo "394770 registro(s) encontrado(s)" fica em
# ``#navigator .navLeft``. O HTML da página só entra (``fallback_html``)
# quando o seletor não casa nenhum elemento com texto, e lá a expressão
# "registro(s) encontrado(s)" continua específica. Se o seletor casar um
# elemento cujo texto a regex não reconhece, a contagem vem ``None`` e
# ``resolve_total_pages`` levanta.
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
    request_fn("GET", home_url, perfil="cjsg")


# Cabeçalhos do XHR do portal (``x-prototype-version``, ``x-requested-with``).
# ``JSESSIONID`` vai no cookie jar preenchido por :func:`populate_session`.
_XHR_HEADERS = {
    'accept': 'text/javascript, text/html, application/xml, text/xml, */*',
    'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'referer': f"{SEARCH_URL}?actionType=pesquisar",
    'x-prototype-version': '1.5.1.1',
    'x-requested-with': 'XMLHttpRequest',
}


class TJPREmentaIndisponivelError(HTTPSemanticError):
    """``visualizarDecisao.do`` respondeu 200 sem o texto da ementa completa."""


# Marcação de página, que o texto da ementa não traz: só o ``<span>`` do destaque.
_TAGS_DE_PAGINA = frozenset({"html", "head", "body", "title", "script", "form", "table", "div"})


def get_ementa_completa(request_fn: RequestFn, action_type: str, id_registro: str, criterio: str) -> str:
    """Busca o texto completo de uma ementa truncada em "Leia mais..".

    ``action_type`` é ``"exibirTextoCompleto"`` nas linhas do TJ e
    ``"exibirTextoCompletoCidh"`` nas da Corte IDH. A resposta é texto puro,
    com quebras de linha próprias e o termo buscado em ``<span class='high'>``,
    às vezes no meio da palavra ("<span>DANO</span>S MORAIS"); por isso o texto
    sai sem separador entre os nós. O ``criterio`` só muda esse destaque.

    Raises:
        TJPREmentaIndisponivelError: Quando a resposta vem vazia (id que o
            portal não conhece) ou traz marcação de página, como a do portal.
    """
    # ``params`` codifica o termo: "&" ou "#" num f-string cortariam o ``criterio``.
    params = {"actionType": action_type, "idProcesso": id_registro, "criterio": criterio}
    resp = request_fn("GET", VISUALIZAR_URL, params=params, headers=_XHR_HEADERS, perfil="ementa")
    soup = BeautifulSoup(resp.text, "html.parser")
    texto = str(soup.get_text()).strip()
    if not texto or soup.find(_TAGS_DE_PAGINA) is not None:
        raise TJPREmentaIndisponivelError(f"TJPR: {action_type} de {id_registro!r} não trouxe o texto da ementa.")
    return texto


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


def _last_page_links(soup: BeautifulSoup, pagina: int) -> set[int]:
    """Lê os totais dos links "Última Página" da ``pagina`` inteira.

    Ativo, o link é ``a.arrowLastOn`` e o href em JavaScript carrega
    ``['pageNumber'].value='<total>'``. Desativado, o portal desenha a mesma
    âncora com classe ``arrowLastOff`` e sem href, o que na primeira página
    quer dizer total 1; nas demais, quer dizer que a ``pagina`` é a última, e
    o link desativado não entra na conferência. A busca cobre a página
    inteira, e não só o ``#navigator .navRight``, para que um contêiner
    renomeado não esconda o link da conferência.
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
    if pagina == 1 and soup.select_one("a.arrowLastOff") is not None:
        totais.add(1)
    return totais


def extract_total_pages(html: str, pagina: int = 1) -> int:
    """Extrai o total de páginas de uma página de resultados do TJPR, a ``pagina``.

    O total sai da contagem "N registro(s) encontrado(s)" dividida por
    ``RESULTS_PER_PAGE``, e os links "Última Página" (ativos e desativados)
    são conferidos contra ele por
    :func:`~juscraper.utils.pagination.resolve_total_pages`. O paginador não
    exibe "Página X de Y", e o maior ``pageNumber`` visível é o fim da janela
    de links (3 na página 1), não o total. :func:`cjsg_download` lê a menor
    página pedida, que pode ser a última, onde "Última" vem desativada.

    Raises:
        ValueError: Nos casos de :func:`~juscraper.utils.pagination.resolve_total_pages`
            e de :func:`~juscraper.utils.pagination.parse_page_number`.
    """
    soup = BeautifulSoup(html, "html.parser")
    n_resultados = extract_count_with_cascade(
        soup,
        css_selectors=_COUNT_SELECTORS,
        regex_patterns=_COUNT_PATTERNS,
        fallback_html=True,
    )
    return resolve_total_pages(
        n_resultados,
        resultados_por_pagina=RESULTS_PER_PAGE,
        totais_links=_last_page_links(soup, pagina),
        tribunal="TJPR",
    )


def cjsg_download(
    home_url: str,
    pesquisa: str,
    paginas: Paginas | None = None,
    data_julgamento_inicio=None,
    data_julgamento_fim=None,
    data_publicacao_inicio=None,
    data_publicacao_fim=None,
    *,
    request_fn: RequestFn,
    ler_parcial: Callable[[list[str]], pd.DataFrame],
    sleep_time: float = 1.0,
) -> list:
    """
    Downloads raw results from the TJPR 'jurisprudence search' (multiple pages).
    Returns a list of HTMLs (one per page).

    Raises:
        ColetaParcialError: Uma página falhou depois de outras baixadas;
            ``resultado`` é ``ler_parcial`` das baixadas
            (:func:`juscraper.utils.pagination.baixar_paginas_pedidas`).
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
        resp = request_fn("POST", url, data=data, headers=headers, perfil="cjsg")
        return resp.text

    # O total vem da menor página pedida, também com ``paginas`` explícito: a
    # pedida além do total vai para o log, sem requisição.
    return baixar_paginas_pedidas(
        paginas,
        _fetch_page,
        functools.partial(extract_total_pages, pagina=menor_pagina(paginas)),
        tribunal="TJPR",
        sleep_time=sleep_time,
        ler_parcial=ler_parcial,
        mensagem_parcial=_mensagem_parcial,
    )


def _mensagem_parcial(faltando: list[int], n_baixadas: int, exc: Exception) -> str:
    """Texto do ``ColetaParcialError``: o padrão, com o aviso das ementas truncadas no parcial."""
    return mensagem_de_coleta_parcial("TJPR cjsg", faltando, n_baixadas, exc) + (
        " No parcial, as ementas longas vêm truncadas em \"Leia mais..\": o portal acabou de falhar, "
        "e a ementa completa custaria uma requisição por linha."
    )
