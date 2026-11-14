"""Offline contract tests for TJPR cjsg.

TJPR's flow:

1. ``GET /jurisprudencia/`` lands ``JSESSIONID`` in the session cookie
   jar (the scraper hits this endpoint once per ``cjsg`` call, in
   ``cjsg_download``).
2. ``POST /jurisprudencia/publico/pesquisa.do?actionType=pesquisar``
   per page (``pageNumber``, 1-based, ``pageSize=50``: the portal always
   returns 50 rows, and a smaller ``pageSize`` only inflates the "Última" link).
3. For each row whose ementa is truncated with "Leia mais...", an
   extra ``GET visualizarDecisao.do?actionType=exibirTextoCompleto&idProcesso=...``
   is issued by ``cjsg_parse``.

The contract registers a single response for each kind of request;
``responses`` reuses registered responses across calls by default, so
the ementa GETs (×N) all share one fixture.
"""
import re

import pandas as pd
import pytest
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjpr.download import VISUALIZAR_URL, build_cjsg_form_body
from tests._helpers import load_sample, query_param_subset_matcher
from tests.tjpr._helpers import SEARCH_URL, add_ementa_completa, add_home, add_search_page

CJSG_MIN_COLUMNS = {"processo", "orgao_julgador", "relator", "data_julgamento", "ementa"}


@responses.activate
def test_cjsg_typical_com_paginacao(mocker):
    """Two-page query exercises ``pageNumber=1`` and ``pageNumber=2``."""
    mocker.patch("time.sleep")
    add_home()
    add_search_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    add_search_page("dano moral", 2, "cjsg/results_normal_page_02.html")
    add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("dano moral", paginas=range(1, 3))

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    # 50 linhas por página, das quais 10 são da Corte IDH e ficam de fora.
    assert len(df) == 80
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    # Nestes samples, só as linhas da Corte IDH vinham sem processo.
    assert (df["processo"] != "").all(), "processo vazio: linha da Corte IDH no resultado?"
    assert df["processo"].nunique() > 1, (
        "todos os processos iguais — paginação suspeita"
    )
    # A ementa completa vem de ``visualizarDecisao.do``; ``pesquisa.do``
    # devolvia a página do portal, com o menu da intranet no lugar da ementa.
    assert not df["ementa"].str.contains("Intranet|Leia mais|Erro ao buscar").any()
    # A nota do portal sobre onde o termo apareceu não faz parte da ementa.
    assert not df["ementa"].str.contains("A expressão foi encontrada").any()
    # O destaque ``<span class='high'>DANO</span>S`` não parte a palavra.
    assert df["ementa"].str.contains("INDENIZAÇÃO POR DANOS MORAIS. SERVIÇOS BANCÁRIOS").any()
    assert not df["ementa"].str.contains("DANO\nS", regex=False).any()


@responses.activate
def test_cjsg_single_page(mocker):
    """Busca real de página única ("quilombola", 5 resultados judiciais)."""
    mocker.patch("time.sleep")
    add_home()
    add_search_page("quilombola", 1, "cjsg/single_page.html")
    add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("quilombola", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) == 5
    assert df["processo"].notna().all(), "processo nulo em alguma linha"
    # Nestes samples, só as linhas da Corte IDH vinham sem processo.
    assert (df["processo"] != "").all(), "processo vazio: linha da Corte IDH no resultado?"


@responses.activate
def test_cjsg_paginas_none_pagina_unica_baixa_so_a_primeira(mocker):
    """``paginas=None`` numa busca de página única lê "Última" desativada e para na página 1.

    Além da home e da página 1, as únicas requisições são os GETs de ementa
    completa das linhas com "Leia mais...", que ``cjsg_parse`` dispara.
    """
    mocker.patch("time.sleep")
    add_home()
    add_search_page("quilombola", 1, "cjsg/single_page.html")
    add_ementa_completa()

    df = jus.scraper("tjpr").cjsg("quilombola", paginas=None)

    assert len(df) == 5
    busca = [call for call in responses.calls if "exibirTextoCompleto" not in call.request.url]
    assert [call.request.method for call in busca] == ["GET", "POST"]


@responses.activate
def test_cjsg_paginas_none_sem_contagem_levanta(mocker):
    """Primeira página sem a contagem de registros não informa o total: levanta, nunca estima.

    A contagem "N registro(s) encontrado(s)" é a fonte do total; sem ela,
    ``paginas=None`` baixava uma página só em silêncio. O erro sai depois da
    home e da primeira página, antes de qualquer outra.
    """
    mocker.patch("time.sleep")
    add_home()
    contagem = re.compile(r"[0-9]+ registro\(s\) encontrado\(s\)")
    html = load_sample("tjpr", "cjsg/results_normal_page_01.html")
    assert len(contagem.findall(html)) == 2
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=contagem.sub("", html),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_params_matcher(build_cjsg_form_body("dano moral", page=1), allow_blank=True),
        ],
    )

    with pytest.raises(ValueError, match="não traz a contagem"):
        jus.scraper("tjpr").cjsg("dano moral", paginas=None)

    assert len(responses.calls) == 2


@responses.activate
def test_cjsg_no_results(mocker):
    """Zero-hit query returns an empty DataFrame."""
    mocker.patch("time.sleep")
    add_home()
    add_search_page("juscraper_probe_zero_hits_xyzqwe", 1, "cjsg/no_results.html")

    df = jus.scraper("tjpr").cjsg("juscraper_probe_zero_hits_xyzqwe", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_ementa_completa_5xx_persistente(mocker):
    """Falha persistente no fetch da ementa-completa nao derruba o DataFrame.

    Quando o GET ``visualizarDecisao.do?actionType=exibirTextoCompleto`` devolve 5xx em todas as
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
    add_search_page("quilombola", 1, "cjsg/single_page.html")
    responses.add(
        responses.GET,
        VISUALIZAR_URL,
        body="<html>upstream error</html>",
        status=503,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )

    df = jus.scraper("tjpr").cjsg("quilombola", paginas=1)

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJSG_MIN_COLUMNS
    assert len(df) > 0, "DataFrame vazio — fetch da ementa-completa quebrou o parse inteiro"
    erros = df["ementa"].astype(str).str.contains(
        r"\[Erro ao buscar ementa completa", regex=True, na=False
    )
    assert erros.any(), (
        "nenhuma linha recebeu o sufixo de erro — fixture nao acionou o "
        "fallback de ementa-completa (verificar 'Leia mais...' no sample)"
    )


def test_build_cjsg_form_body_envia_page_size_50():
    """O portal devolve 50 linhas por página e desenha o link "Última" com o ``pageSize`` enviado.

    Literal de propósito: os matchers dos outros contratos usam o próprio
    ``build_cjsg_form_body`` como valor esperado e não pegariam a volta do
    ``pageSize=10``, que inflava o link 5 vezes.
    """
    assert build_cjsg_form_body("dano moral", page=1)["pageSize"] == "50"
