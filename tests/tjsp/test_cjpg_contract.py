"""Offline contract tests for TJSP cjpg.

Mocks ``cjpg/pesquisar.do`` (page 1) and ``cjpg/trocarDePagina.do`` (page
2+) with live-captured samples. Validates the public DataFrame contract and
the query-string payload.

Samples exercised (all captured by ``tests/fixtures/capture/tjsp.py``):

- ``cjpg/results_normal_page_01.html`` / ``_02.html`` — ``dano moral``,
  used for multi-page coverage ("Resultados 1 a 10 de 3565472").
- ``cjpg/single_page.html`` — ``jurimétrica``, 2 sentences in one page.
- ``cjpg/no_results.html`` — eSAJ form page returned when the query
  matches zero acórdãos. Guards the fix for #109.
"""
import pandas as pd
import pytest
import requests
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.base import _texto_ausente_como_none
from juscraper.core.exceptions import ColetaParcialError
from juscraper.courts._esaj.cjpg_parse import cjpg_n_results
from juscraper.courts.tjsp.exceptions import QueryTooLongError
from tests._helpers import load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjpg_params

BASE = "https://esaj.tjsp.jus.br/cjpg"
CJPG_MIN_COLUMNS = {"cd_processo", "id_processo", "classe", "relator", "decisao"}

# Página de erro do eSAJ no meio da coleta. Não há captura de captcha do
# CJPG; o HTML mínimo fica aqui, e não em ``samples/``.
PAGINA_CAPTCHA = (
    '<!DOCTYPE html><html><body><div class="mensagemErro">'
    "Falha na verificação do captcha. Nenhum resultado encontrado."
    "</div></body></html>"
)


def _add_pesquisar(pesquisa: str, sample_path: str) -> None:
    # ``requests`` drops keys whose value is ``None``, so the matcher must
    # expect the same filtered dict. Empty strings are kept (``key=``).
    expected = {k: v for k, v in make_tjsp_cjpg_params(pesquisa).items() if v is not None}
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )


def _add_trocar_de_pagina(pagina: int, sample_path: str) -> None:
    # cjpg_download.py:139 builds the URL as a literal f-string with an
    # empty conversationId (``?pagina=N&conversationId=``). The matcher
    # mirrors that — conversationId="" is sent as ``conversationId=``.
    responses.add(
        responses.GET,
        f"{BASE}/trocarDePagina.do",
        body=load_sample_bytes("tjsp", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"pagina": str(pagina), "conversationId": ""})],
    )


@responses.activate
def test_cjpg_single_page(tmp_path, mocker):
    """Busca cujos resultados cabem numa página — DataFrame with schema."""
    mocker.patch("time.sleep")
    _add_pesquisar("jurimétrica", "cjpg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "jurimétrica", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJPG_MIN_COLUMNS
    assert len(df) == 2


@responses.activate(registry=OrderedRegistry)
def test_cjpg_multi_page(tmp_path, mocker):
    """Multi-page: GET pesquisar.do (page 1) + GET trocarDePagina.do (page 2)."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    _add_trocar_de_pagina(2, "cjpg/results_normal_page_02.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral", paginas=range(1, 3)
    )

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= CJPG_MIN_COLUMNS
    # 10 rows per page; cjpg_download.py:114 clamps range.stop to n_pags+1
    # which is large here, so both pages are fetched.
    assert len(df) == 20


@responses.activate
def test_cjpg_paginas_alem_do_total_devolve_vazio(tmp_path, mocker):
    """Página pedida além do total não gera arquivo, e o resultado é vazio.

    ``single_page.html`` traz 2 resultados, uma página de 10. Só a página 1 é
    requisitada; nenhuma página entra no diretório baixado.
    """
    mocker.patch("time.sleep")
    _add_pesquisar("jurimétrica", "cjpg/single_page.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("jurimétrica", paginas=[5])

    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjpg_no_results(tmp_path, mocker):
    """Zero-result query returns an empty DataFrame instead of raising."""
    mocker.patch("time.sleep")
    _add_pesquisar("juscraper_probe_zero_hits_xyzqwe", "cjpg/no_results.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "juscraper_probe_zero_hits_xyzqwe", paginas=1
    )

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_cjpg_query_too_long_raises(tmp_path):
    """Pre-request guard: a pesquisa > 120 chars must raise before any HTTP."""
    pesquisa = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(QueryTooLongError):
        scraper.cjpg(pesquisa, paginas=1)


def test_cjpg_query_too_long_via_alias_raises(tmp_path):
    """Pre-request guard tambem cobre o caso do alias `query` resolvido pelo
    pipeline (refs #174 — validate_pesquisa_length roda apos consumir
    o alias)."""
    long_query = "a" * 121
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(DeprecationWarning), pytest.raises(QueryTooLongError):
        scraper.cjpg(paginas=1, query=long_query)


@responses.activate
def test_cjpg_count_only_returns_int(tmp_path, mocker):
    """``count_only=True`` short-circuits to int after the initial GET (#92)."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral", count_only=True,
    )

    assert isinstance(n, int)
    assert n == 3565472  # "Resultados 1 a 10 de 3565472" no sample
    # Apenas 1 GET (pesquisar.do); nenhum trocarDePagina.do.
    assert len(responses.calls) == 1


@responses.activate
def test_cjpg_count_only_zero_results(tmp_path, mocker):
    """``count_only=True`` em busca sem hits retorna 0 (issue #92)."""
    mocker.patch("time.sleep")
    _add_pesquisar("juscraper_probe_zero_hits_xyzqwe", "cjpg/no_results.html")

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "juscraper_probe_zero_hits_xyzqwe", count_only=True,
    )

    assert n == 0


@responses.activate(registry=OrderedRegistry)
def test_cjpg_count_only_sums_across_chunks(tmp_path, mocker):
    """``count_only=True`` + janela > 366d soma contagens cross-window (#92).

    Mocka 2 GETs distintos com `data_inicio` diferente (uma janela cada) e
    afere que o total e a soma das contagens reportadas. Vai falhar se o
    auto_chunk count-only path quebrar (ex.: iterar fora de
    `iter_date_windows` ou nao somar). A soma esperada vem da contagem de
    cada sample, porque a do ``single_page.html`` hoje sai errada (ver
    ``test_single_page_conta_os_dois_resultados`` em ``test_cjpg.py``).
    """
    mocker.patch("time.sleep")
    # Janela total: 02/01/2020 a 01/01/2022 = 2 anos de calendario = 2 janelas.
    # Janela 1: 02/01/2020 -> 01/01/2021. Janela 2: 02/01/2021 -> 01/01/2022.
    expected_w1 = {
        k: v for k, v in make_tjsp_cjpg_params("dano moral").items() if v is not None
    }
    expected_w1["dadosConsulta.dtInicio"] = "02/01/2020"
    expected_w1["dadosConsulta.dtFim"] = "01/01/2021"
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/results_normal_page_01.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected_w1)],
    )

    expected_w2 = dict(expected_w1)
    expected_w2["dadosConsulta.dtInicio"] = "02/01/2021"
    expected_w2["dadosConsulta.dtFim"] = "01/01/2022"
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/single_page.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected_w2)],
    )

    n = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral",
        data_julgamento_inicio="02/01/2020",
        data_julgamento_fim="01/01/2022",
        count_only=True,
    )

    assert isinstance(n, int)
    contagens = [
        cjpg_n_results(load_sample_bytes("tjsp", f"cjpg/{sample}"))
        for sample in ("results_normal_page_01.html", "single_page.html")
    ]
    assert n == sum(contagens)  # soma bruta cross-janela
    assert contagens[0] == 3565472
    assert len(responses.calls) == 2


@responses.activate(registry=OrderedRegistry)
def test_todo_pedido_do_cjpg_tem_timeout(tmp_path, mocker):
    """pesquisar.do e trocarDePagina.do saem com prazo: conexão parada não trava a coleta (#484)."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    _add_trocar_de_pagina(2, "cjpg/results_normal_page_02.html")

    jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(responses.calls) == 2
    assert [c.request.req_kwargs.get("timeout") is not None for c in responses.calls] == [True, True]


@responses.activate(registry=OrderedRegistry)
def test_cjpg_pagina_que_falha_no_parse_levanta_coleta_parcial(tmp_path, mocker):
    """Página fora do formato não some do resultado (#460): o erro sobe com a página lida em ``.resultado``.

    A página 2 é a captura real com um rótulo sem os dois-pontos, como num
    layout novo do eSAJ. Antes, ela saía só no log e o ``cjpg`` devolvia 10
    decisões como se fossem todas.
    """
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    pagina_2 = load_sample_bytes("tjsp", "cjpg/results_normal_page_02.html").replace(b"Classe:", b"Classe", 1)
    responses.add(
        responses.GET,
        f"{BASE}/trocarDePagina.do",
        body=pagina_2,
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"pagina": "2", "conversationId": ""})],
    )

    falha_na_pagina_2 = r"cjpg: 1 de 2 página\(s\) falharam: cjpg_00002\.html\."
    with pytest.raises(ColetaParcialError, match=falha_na_pagina_2) as erro:
        jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(erro.value.resultado) == 10
    assert set(erro.value.resultado.columns) >= CJPG_MIN_COLUMNS
    # O parcial sai no formato do retorno completo, com ``None`` no texto ausente.
    pd.testing.assert_frame_equal(erro.value.resultado, _texto_ausente_como_none(erro.value.resultado))
    assert len(erro.value.falhas) == 1
    assert not list(tmp_path.rglob("*.html"))


@responses.activate(registry=OrderedRegistry)
def test_cjpg_pagina_de_erro_no_meio_da_coleta_levanta_coleta_parcial(tmp_path, mocker):
    """Página de captcha na página 2 não conta como página lida sem resultados."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    responses.add(
        responses.GET,
        f"{BASE}/trocarDePagina.do",
        body=PAGINA_CAPTCHA,
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"pagina": "2", "conversationId": ""})],
    )

    with pytest.raises(ColetaParcialError, match=r"cjpg_00002\.html.*Captcha") as erro:
        jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(erro.value.resultado) == 10


@responses.activate(registry=OrderedRegistry)
def test_cjpg_pagina_com_status_de_erro_e_pedida_de_novo(tmp_path, mocker):
    """Página 2 que volta 503 e depois 200 entra inteira: o erro passageiro não perde a página."""
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    responses.add(responses.GET, f"{BASE}/trocarDePagina.do", status=503)
    responses.add(responses.GET, f"{BASE}/trocarDePagina.do", body=requests.ConnectionError("recusada"))
    _add_trocar_de_pagina(2, "cjpg/results_normal_page_02.html")

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(df) == 20
    assert len(responses.calls) == 4


@responses.activate
def test_cjpg_pagina_que_falha_em_todas_as_tentativas_levanta_coleta_parcial(tmp_path, mocker):
    """Página 2 com 500 em todas as tentativas não vira página vazia (#460): sobe com a página 1 lida.

    Antes, o HTML da página de erro era gravado como a página 2 e lido sem
    resultados, e o ``cjpg`` devolvia 10 decisões como se fossem todas.
    """
    mocker.patch("time.sleep")
    _add_pesquisar("dano moral", "cjpg/results_normal_page_01.html")
    responses.add(responses.GET, f"{BASE}/trocarDePagina.do", body="<html>erro</html>", status=500)

    with pytest.raises(ColetaParcialError, match=r"cjpg_00002\.html.*página 2 não baixada após 5 tentativas.*500"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cjpg("dano moral", paginas=range(1, 3))

    assert len(responses.calls) == 1 + 5
