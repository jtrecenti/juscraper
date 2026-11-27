"""Downloads raw results from the TJSC jurisprudence search (eproc PHP)."""
import re

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import baixar_paginas_pedidas, extract_count_with_cascade, resolve_total_pages

# Host novo; o antigo, eproc1g.tjsc.jus.br/eproc, redireciona para cá (#495).
CONTROLADOR_URL = "https://eprocwebcon.tjsc.jus.br/consulta1g/externo_controlador.php"
SEARCH_URL = f"{CONTROLADOR_URL}?acao=jurisprudencia@jurisprudencia/listar_resultados"
AJAX_URL = f"{CONTROLADOR_URL}?acao=jurisprudencia@jurisprudencia/ajax_paginar_resultado"
RESULTS_PER_PAGE = 10
#: Perfil HTTP da busca, declarado em ``TJSCScraper.perfis_http``.
PERFIL_CJSG = "cjsg"
#: ``buscar_em`` -> valor de ``rdoCampo`` no formulário do portal.
RDO_CAMPO = {"ementa": "E", "inteiro_teor": "I"}


def build_cjsg_form_body(
    pesquisa: str,
    page: int = 1,
    buscar_em: str = "ementa",
    processo: str = "",
    dt_decisao_inicio: str = "",
    dt_decisao_fim: str = "",
    dt_publicacao_inicio: str = "",
    dt_publicacao_fim: str = "",
    num_resultados: int = RESULTS_PER_PAGE,
) -> dict:
    """Build the form-encoded body for the TJSC CJSG eproc endpoint.

    ``buscar_em`` (``"ementa"`` ou ``"inteiro_teor"``) vai em ``rdoCampo``
    com os valores do portal, ``"E"`` ou ``"I"``.
    """
    return {
        "txtPesquisa": pesquisa,
        "rdoCampo": RDO_CAMPO[buscar_em],
        "txtProcesso": processo,
        "dtDecisaoInicio": dt_decisao_inicio,
        "dtDecisaoFim": dt_decisao_fim,
        "dtPublicacaoInicio": dt_publicacao_inicio,
        "dtPublicacaoFim": dt_publicacao_fim,
        "hdnPaginaAtual": str(page),
        "numResultadosPorPagina": str(num_resultados),
    }


def cjsg_url_for_page(page: int) -> str:
    """Return the TJSC CJSG endpoint URL for a given 1-based page number."""
    return AJAX_URL if page > 1 else SEARCH_URL


# Sem o ``h2`` (``fallback_html``), a regex roda no HTML da página: o rótulo
# "N documentos encontrados" inteiro é o que ela exige.
_PAGINATION_CSS_SELECTORS: tuple[str, ...] = ("h2.mb-0",)
_PAGINATION_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"(\d+)\s*documentos?\s*encontrados?", re.IGNORECASE),
)


def _get_total_pages(html: str, per_page: int = RESULTS_PER_PAGE) -> int:
    """Total de páginas pela contagem "N documentos encontrados".

    A busca vazia traz "0 documentos encontrados" e dá 1 página; sem a
    contagem (markup novo, página de erro), :func:`resolve_total_pages` levanta.
    """
    total = extract_count_with_cascade(
        html,
        css_selectors=_PAGINATION_CSS_SELECTORS,
        regex_patterns=_PAGINATION_REGEXES,
        fallback_html=True,
    )
    return resolve_total_pages(total, resultados_por_pagina=per_page, tribunal="TJSC")


def cjsg_download_manager(
    pesquisa: str,
    paginas=None,
    *,
    request_fn: RequestFn,
    sleep_time: float = 1.0,
    **kwargs,
) -> list:
    """Download raw HTML results from the TJSC jurisprudence search.

    Returns a list of raw HTML strings (one per page).

    Args:
        pesquisa: Search term.
        paginas (list, range, or None): Pages to download (1-based).
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJSCScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx.
        sleep_time: Delay (em segundos) entre páginas. Default 1.0; o client
            normalmente passa ``self.sleep_time`` herdado de ``HTTPScraper``.
        **kwargs: Additional filter parameters.

    Raises:
        ValueError: Quando a página lida não traz "N documentos encontrados" (markup novo).
    """
    def _get_page(pagina_1based: int) -> str:
        data = build_cjsg_form_body(pesquisa=pesquisa, page=pagina_1based, **kwargs)
        url = cjsg_url_for_page(pagina_1based)
        # Seguir um redirecionamento transformaria o POST em GET sem o
        # formulário: a busca voltaria sem termo nem filtros, sem erro (#495).
        resp = request_fn(
            "POST", url, data=data, allow_redirects=False, perfil=PERFIL_CJSG,
        )
        if 300 <= resp.status_code < 400:
            raise RuntimeError(
                f"TJSC: busca redirecionada (HTTP {resp.status_code}) para "
                f"{resp.headers.get('Location')!r}; o portal mudou de endereço."
            )
        # O portal declara ISO-8859-1 em todas as páginas. O palpite de
        # ``apparent_encoding`` dava windows-1250 nas da paginação AJAX e
        # trocava "ã" por "ă" ("Apelaçăo").
        resp.encoding = "ISO-8859-1"
        return resp.text

    # Toda página traz o total no cabeçalho, inclusive as da paginação AJAX.
    return baixar_paginas_pedidas(paginas, _get_page, _get_total_pages, tribunal="TJSC", sleep_time=sleep_time)
