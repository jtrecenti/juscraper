"""Offline contract tests for TJPR cjsg.

TJPR's flow:

1. ``GET /jurisprudencia/`` lands ``JSESSIONID`` in the session cookie
   jar (the scraper hits this endpoint once per ``cjsg`` call, in
   ``cjsg_download``).
2. ``POST /jurisprudencia/publico/pesquisa.do?actionType=pesquisar``
   per page (``pageNumber``, 1-based, ``pageSize=10``).
3. For each row whose ementa is truncated with "Leia mais...", an
   extra ``GET ?actionType=exibirTextoCompleto&idProcesso=...`` is
   issued by ``cjsg_parse``.

The contract registers a single response for each kind of request;
``responses`` reuses registered responses across calls by default, so
the ementa GETs (×N) all share one fixture.
"""
import pandas as pd
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjpr.download import build_cjsg_form_body
from tests._helpers import load_sample, query_param_subset_matcher
from tests.tjpr._helpers import SEARCH_URL, add_home

CJSG_MIN_COLUMNS = {"processo", "orgao_julgador", "relator", "data_julgamento", "ementa"}


def _add_search_page(pesquisa: str, pagina: int, sample_path: str):
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_params_matcher(
                build_cjsg_form_body(pesquisa, page=pagina),
                allow_blank=True,
            ),
        ],
    )


def _add_ementa_completa():
    """Single response shared by every ``actionType=exibirTextoCompleto`` GET.

    As of 2026-04 the upstream endpoint returns a generic Struts error page
    regardless of ``idProcesso``/``criterio``; we capture one and reuse it.
    """
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/ementa_completa.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises ``pageNumber=1`` and ``pageNumber=2``."""
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_search_page("dano moral", 2, "cjsg/results_normal_page_02.html")
    _add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    # Linhas com processo vazio existem legitimamente no TJPR (sigilo,
    # rows de cabeçalho, etc.); só falha se a maioria estiver vazia
    # (sinal de parser quebrado).
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginação suspeita"
    )


@responses.activate
def test_cjsg_single_page(mocker):
    """Single page scenario."""
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("direito civil", 1, "cjsg/single_page.html")
    _add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("direito civil", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    # Linhas com processo vazio existem legitimamente no TJPR (sigilo,
    # rows de cabeçalho, etc.); só falha se a maioria estiver vazia
    # (sinal de parser quebrado).
    assert (df["processo"].astype(str).str.len() > 0).mean() >= 0.5, (
        "mais da metade dos processos vazios — parser provavelmente quebrado"
    )


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjpr").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_ementa_completa_5xx_persistente(mocker):
    """Falha persistente no fetch da ementa-completa nao derruba o DataFrame.

    Quando o GET ``actionType=exibirTextoCompleto`` devolve 5xx em todas as
    tentativas, ``HTTPScraper._request_with_retry`` levanta
    ``RetryExhaustedError``. O ``try/except`` row-level em ``cjsg_parse``
    deve capturar essa excecao (alem de ``requests.RequestException``) para
    preservar a degradacao graciosa: o DataFrame retorna com todas as rows
    parseadas e a ementa truncada ganha o sufixo ``[Erro ao buscar ementa
    completa: ...]`` apenas nas linhas afetadas. Cobre o gap entre o regime
    antigo (``session.get(...).raise_for_status()`` -> ``HTTPError`` =
    ``RequestException``, capturada) e o novo regime via ``HTTPScraper``
    (``RetryExhaustedError``, que **nao** herda de ``RequestException``).
    """
    mocker.patch("time.sleep")
    add_home()
    _add_search_page("dano moral", 1, "cjsg/single_page.html")
    responses.add(
        responses.GET,
        SEARCH_URL,
        body="<html>upstream error</html>",
        status=503,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )

    df = jus.scraper("tjpr").cjsg("dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert CJSG_MIN_COLUMNS <= set(df.columns)
    assert len(df) > 0, "DataFrame vazio — fetch da ementa-completa quebrou o parse inteiro"
    erros = df["ementa"].astype(str).str.contains(
        r"\[Erro ao buscar ementa completa", regex=True, na=False
    )
    assert erros.any(), (
        "nenhuma linha recebeu o sufixo de erro — fixture nao acionou o "
        "fallback de ementa-completa (verificar 'Leia mais...' no sample)"
    )
