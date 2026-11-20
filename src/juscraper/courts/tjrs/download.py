"""Downloads raw files from the TJRS jurisprudence search."""
import math
from collections.abc import Callable
from urllib.parse import urlencode

from juscraper.core.exceptions import ColetaParcialError
from juscraper.core.http import RequestFn
from juscraper.utils.pagination import baixar_paginas_guardando_parcial, descrever_paginas

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


def _coleta_parcial(resultados: list[dict], faltando: list[int], exc: Exception) -> ColetaParcialError:
    """``ColetaParcialError`` com as páginas baixadas antes de ``faltando[0]`` falhar."""
    mensagem = (
        f"TJRS cjsg: a página {faltando[0]} falhou ({exc!r}), e a busca parou. "
        f"As {len(resultados)} página(s) baixadas antes estão, já lidas, no atributo .resultado do erro; "
        f"faltam as páginas {descrever_paginas(faltando)}, que podem ser pedidas de novo com paginas=."
    )
    return ColetaParcialError(mensagem, resultado=cjsg_parse_manager(resultados), falhas=[(None, None, exc)])


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
    paginas=None,
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
    **kwargs,
) -> list:
    """
    Downloads raw files from the TJRS jurisprudence search (multiple pages).
    Returns a list of raw files (JSON).

    Args:
        paginas (list, range, or None): Pages to download (1-based).
            None: downloads all available pages.
        request_fn: HTTP callable that handles retry + raise_for_status — em
            uso normal e ``TJRSScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando backoff exponencial
            para 429/5xx. Recebe ``perfil=PERFIL_CJSG`` em toda requisição.
        secao: 'civel', 'crime', or None.
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

    if paginas is None:
        first = _fetch_page(1)
        num_found = first.get('response', {}).get('numFound', 0)
        n_pags = math.ceil(num_found / RESULTS_PER_PAGE) if num_found else 1
        if n_pags == 1:
            return [first]
        return _baixar_paginas(_fetch_page, list(range(2, n_pags + 1)), [first])

    return _baixar_paginas(_fetch_page, list(paginas), [])


def _baixar_paginas(buscar: Callable[[int], dict], paginas: list[int], resultados: list[dict]) -> list[dict]:
    """Acrescenta ``paginas`` a ``resultados``; a que falha com outra já baixada sobe como ``ColetaParcialError``.

    Vale para toda falha da página (rede depois das tentativas, corpo que não
    é JSON, erro do Solr), como no TJPR, no TJMG e no TJTO.
    """
    return baixar_paginas_guardando_parcial(
        buscar, paginas, resultados, coleta_parcial=_coleta_parcial, desc="Baixando páginas TJRS"
    )
