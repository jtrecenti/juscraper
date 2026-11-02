"""Offline contract tests for TJSP cpopg (both ``method='html'`` and ``'api'``).

Mocks the request flows against samples captured by
``tests/fixtures/capture/tjsp.py``. Validates that the public ``.cpopg()``
call returns a dict of DataFrames with the expected keys and minimum
schema, for both transports.

HTML flow: GET ``cpopg/search.do?…`` → scraper extracts one
``processo.codigo`` → saves the search response itself (the eSAJ returns
the process details directly when the CNJ is unique).

API flow: GET ``processo/cpopg/search/numproc/{id}`` → POST
``processo/cpopg/dadosbasicos/{cd}`` → four GETs for partes/movimentacao/
incidente/audiencia. Order is not enforced via ``OrderedRegistry`` because
it's an implementation detail — ``responses`` matchers already pin each
endpoint to its sample.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"
API = "https://api.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"
CD_PROCESSO = "9M0002CYG0000"
CNJ_DIGITS = "10001497120248260346"

# Schema keys differ between HTML and API transports by design: the HTML
# parse collapses 'movimentacao' into 'movimentacoes' and groups 'peticoes
# diversas'; the API parse keeps the singular resource names from the JSON.
CPOPG_HTML_KEYS = {"basicos", "partes", "movimentacoes", "peticoes_diversas"}
CPOPG_API_KEYS = {"basicos", "partes", "movimentacao", "incidente", "audiencia"}
CPOPG_BASICOS_MIN = {"id_processo", "classe", "assunto"}


# ---------- method='html' -----------------------------------------------

@responses.activate
def test_cpopg_html_single_match(tmp_path, mocker):
    """HTML flow: search.do returns the process page directly (1 match)."""
    mocker.patch("time.sleep")
    search_params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dadosConsulta.valorConsultaNuUnificado": CNJ,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        body=load_sample_bytes("tjsp", "cpopg/search.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ, method="html")

    assert isinstance(result, dict)
    assert set(result.keys()) >= CPOPG_HTML_KEYS
    basicos = result["basicos"]
    assert isinstance(basicos, pd.DataFrame)
    assert set(basicos.columns) >= CPOPG_BASICOS_MIN
    assert len(basicos) == 1
    assert basicos.iloc[0]["id_processo"] == CNJ


# ---------- method='api' ------------------------------------------------

@responses.activate
def test_cpopg_api(tmp_path, mocker):
    """API flow: search/numproc → dadosbasicos → 4 component GETs."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cpopg/api_search.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(
        responses.POST,
        f"{API}/processo/cpopg/dadosbasicos/{CD_PROCESSO}",
        body=load_sample("tjsp", "cpopg/api_dadosbasicos.json"),
        status=200,
        content_type="application/json",
    )
    for comp in ("partes", "movimentacao", "incidente", "audiencia"):
        responses.add(
            responses.GET,
            f"{API}/processo/cpopg/{comp}/{CD_PROCESSO}",
            body=load_sample("tjsp", f"cpopg/api_{comp}.json"),
            status=200,
            content_type="application/json",
        )

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ, method="api")

    assert isinstance(result, dict)
    assert set(result.keys()) >= CPOPG_API_KEYS
    basicos = result["basicos"]
    assert isinstance(basicos, pd.DataFrame)


@responses.activate
def test_cpopg_download_html_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """O destino alternativo do HTML não deve alterar o destino configurado."""
    mocker.patch("time.sleep")
    search_params = {
        "conversationId": "",
        "cbPesquisa": "NUMPROC",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dadosConsulta.valorConsultaNuUnificado": CNJ,
        "dadosConsulta.valorConsulta": "",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        body=load_sample_bytes("tjsp", "cpopg/search.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )
    caminho = tmp_path / "padrao"
    alternativo = tmp_path / "alternativo"
    scraper = jus.scraper("tjsp", download_path=str(caminho))

    scraper.cpopg_download(CNJ, method="html", diretorio=str(alternativo))

    assert (alternativo / "cpopg").is_dir()
    assert not (caminho / "cpopg").exists()
    assert scraper.download_path == str(caminho)


@responses.activate
def test_cpopg_download_api_usa_download_path_sem_diretorio(tmp_path, mocker):
    """Sem destino alternativo, o CPOPG API usa ``self.download_path``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body=load_sample("tjsp", "cpopg/api_search.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(
        responses.POST,
        f"{API}/processo/cpopg/dadosbasicos/{CD_PROCESSO}",
        body=load_sample("tjsp", "cpopg/api_dadosbasicos.json"),
        status=200,
        content_type="application/json",
    )
    for comp in ("partes", "movimentacao", "incidente", "audiencia"):
        responses.add(
            responses.GET,
            f"{API}/processo/cpopg/{comp}/{CD_PROCESSO}",
            body=load_sample("tjsp", f"cpopg/api_{comp}.json"),
            status=200,
            content_type="application/json",
        )
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cpopg_download(CNJ, method="api")

    assert (tmp_path / "cpopg").is_dir()
    assert scraper.download_path == str(tmp_path)


def test_cpopg_download_api_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """O destino alternativo do API deve ser encaminhado ao downloader."""
    caminho = tmp_path / "padrao"
    alternativo = tmp_path / "alternativo"
    scraper = jus.scraper("tjsp", download_path=str(caminho))
    download = mocker.patch("juscraper.courts.tjsp.client.cpopg_download_api")

    scraper.cpopg_download(CNJ, method="api", diretorio=str(alternativo))

    assert download.call_args.kwargs["download_path"] == str(alternativo)
    assert scraper.download_path == str(caminho)


# ---------- method='html': movimentações sob demanda ---------------------

# Cumprimento de sentença com nomes de pessoa física trocados por fictícios.
# A página vem com "Exibir movimentações"; a lista sai em três páginas do
# carregarMovimentacoesAjax.do (5, 5 e 4 linhas), ligadas pelos cursores.
CNJ_INCIDENTE = "0000564-95.2025.8.26.0068"
CD_INCIDENTE = "1W001DU0E0000"
CURSOR_PAGINA_2 = (
    "Ly37POn0CVp5DMEvd-UxaY_2NU4d6snRUMs3hcLnMG0EdZGGdzdjNPqaF1who3O4V5Gz4oZNWEDLN_ZgTQAKiDiLgswAcOEr"
)
CURSOR_PAGINA_3 = (
    "-P67GCMeMTLX-HZTDWpeIXCZboP_NcGh0DigPh9ITLFHb-k4m9J7GtfS3ENX_xjdtriApOPL6TUKA4OYJWVULf64xhjw9AI"
)
URL_MOVIMENTACOES = f"{ESAJ}/cpopg/carregarMovimentacoesAjax.do"


def _registrar_busca_incidente():
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        body=load_sample_bytes("tjsp", "cpopg/show_incidente.html"),
        status=200,
        content_type="text/html;charset=UTF-8",
        match=[query_param_matcher({
            "conversationId": "",
            "cbPesquisa": "NUMPROC",
            "numeroDigitoAnoUnificado": "0000564-95.2025",
            "foroNumeroUnificado": "0068",
            "dadosConsulta.valorConsultaNuUnificado": CNJ_INCIDENTE,
            "dadosConsulta.valorConsulta": "",
            "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        })],
    )


def _registrar_pagina_movimentacoes(pagina, cursor=None, body=None):
    parametros = {"processo.codigo": CD_INCIDENTE, **({"cursor": cursor} if cursor else {})}
    responses.add(
        responses.GET,
        URL_MOVIMENTACOES,
        body=body if body is not None else load_sample_bytes("tjsp", f"cpopg/movimentacoes_pagina_{pagina}.html"),
        status=200,
        content_type="text/html;charset=UTF-8",
        match=[query_param_matcher(parametros)],
    )


def _chamadas(rota):
    return [chamada.request for chamada in responses.calls if chamada.request.url.split("?")[0].endswith(rota)]


@responses.activate
def test_cpopg_html_carrega_todas_as_paginas_de_movimentacoes(tmp_path, mocker):
    """A página só traz o botão; o download segue o cursor até a última página."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ_INCIDENTE, method="html")

    assert [r.params.get("cursor") for r in _chamadas("carregarMovimentacoesAjax.do")] == [
        None, CURSOR_PAGINA_2, CURSOR_PAGINA_3,
    ]
    movimentacoes = result["movimentacoes"]
    assert len(movimentacoes) == 14
    assert movimentacoes["movimento"].ne("").all()
    primeira, ultima = movimentacoes.iloc[0], movimentacoes.iloc[-1]
    assert (primeira["data"], primeira["movimento"]) == (
        "12/11/2025", "Trânsito em Julgado às partes - Proc. em Andamento",
    )
    assert primeira["observacao"].startswith("CERTIDÃO - TRÂNSITO EM JULGADO")
    assert (ultima["data"], ultima["movimento"]) == (
        "27/01/2025", "Execução/Cumprimento de Sentença Iniciada (o)",
    )
    datas = pd.to_datetime(movimentacoes["data"], format="%d/%m/%Y")
    assert datas.is_monotonic_decreasing
    basicos = result["basicos"].iloc[0]
    assert basicos["id_processo"] == CNJ_INCIDENTE
    assert basicos["situacao"] == "Extinto"


@responses.activate
def test_cpopg_html_refaz_a_busca_quando_o_esaj_recusa_as_movimentacoes(tmp_path, mocker):
    """A recusa do eSAJ (div mensagemErroMovimentacoes) refaz a busca, que abre a sessão de novo."""
    mocker.patch("time.sleep")
    recusa = (
        '<div class="mensagemErroMovimentacoes">\n\tNão foi possível realizar a operação '
        "requisitada, tente novamente mais tarde.\n</div>\n"
    )
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1, body=recusa)
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ_INCIDENTE, method="html")

    assert len(_chamadas("search.do")) == 2
    assert len(result["movimentacoes"]) == 14


@responses.activate
def test_cpopg_html_para_quando_o_cursor_se_repete(tmp_path, mocker):
    """Cursor repetido não avança a paginação: o processo fica de fora com erro no log."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    pagina_2 = load_sample("tjsp", "cpopg/movimentacoes_pagina_2.html").replace(CURSOR_PAGINA_3, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2, body=pagina_2)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    erro = mocker.patch("juscraper.courts.tjsp.cpopg_download.logger.error")

    scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert len(_chamadas("carregarMovimentacoesAjax.do")) == 2
    assert "a paginação não avançaria" in str(erro.call_args.args[-1])
    assert not list((tmp_path / "cpopg").rglob("*.html"))



@responses.activate
def test_cpopg_html_para_quando_a_pagina_seguinte_vem_sem_linhas(tmp_path, mocker):
    """Página seguinte sem movimentações não avança a paginação: o processo fica de fora com erro no log."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2, body="")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    erro = mocker.patch("juscraper.courts.tjsp.cpopg_download.logger.error")

    scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert "página sem linhas" in str(erro.call_args.args[-1])
    assert not list((tmp_path / "cpopg").rglob("*.html"))


@responses.activate
def test_cpopg_html_refaz_a_busca_quando_a_primeira_pagina_vem_fora_do_formato(tmp_path, mocker):
    """Primeira página sem a tabela (sessão expirada, por exemplo) é tratada como recusa, não como lista vazia."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1, body="<html><body>Sessão expirada</body></html>")
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ_INCIDENTE, method="html")

    assert len(_chamadas("search.do")) == 2
    assert len(result["movimentacoes"]) == 14

# ---------- method='api': busca sem processo ------------------------------

@responses.activate
def test_cpopg_api_lista_vazia_levanta_erro_explicito(tmp_path, mocker, capsys):
    """A API devolve ``[]`` para o número; o parse explica em vez de levantar KeyError."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body="[]",
        status=200,
        content_type="application/json; charset=utf-8",
    )

    with pytest.raises(ValueError, match="Nenhum arquivo do CPOPG lido"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ, method="api")

    assert "não devolveu nenhum processo" in capsys.readouterr().out
    assert len(responses.calls) == 1
