"""Contratos offline do ``listar_processos`` do STM.

A busca é um GET em ``consulta.php``, na aba de processos do portal
(``search_filter_option=feitos``). Os samples estão descritos em
``samples/processos/README.md``.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.stm.download import BASE_URL, build_processos_params
from juscraper.courts.stm.parse import COLUNAS_PROCESSOS
from tests._helpers import assert_unknown_kwarg_raises, load_sample

INDEX_URL = "https://jurisprudencia.stm.jus.br/index.php"


def _add_page(sample: str, pesquisa: str = "", pagina: int = 1, **filtros) -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("stm", sample),
        content_type="text/html; charset=UTF-8",
        match=[query_param_matcher(build_processos_params(pesquisa, pagina, **filtros))],
    )


@responses.activate
def test_processo_do_stm_por_numero(mocker):
    """Processo de 2º grau: tem relator, não tem juiz nem conselho."""
    mocker.patch("time.sleep")
    _add_page("processos/por_numero.html", "7000374-06.2020.7.00.0000")

    df = jus.scraper("stm").listar_processos("7000374-06.2020.7.00.0000")

    assert responses.calls[0].request.params == {
        "search_filter_option": "feitos",
        "search_filter": "numero",
        "search_input": "7000374-06.2020.7.00.0000",
        "q": "7000374-06.2020.7.00.0000",
        "q_or": "7000374-06.2020.7.00.0000",
        "start": "0",
        "rows": "100",
    }
    assert list(df.columns) == COLUNAS_PROCESSOS
    assert len(df) == 1
    linha = df.iloc[0]
    assert linha["processo"] == "7000374-06.2020.7.00.0000"
    assert linha["classe"] == "HABEAS CORPUS CRIMINAL"
    assert linha["orgao"] == "SUPERIOR TRIBUNAL MILITAR"
    assert linha["relator"] == "JOSÉ COÊLHO FERREIRA"
    assert linha[["revisor", "juiz", "conselho"]].isna().all()
    assert linha["data_autuacao"] == pd.Timestamp("2020-06-08 15:09:43")
    assert linha["situacao"] == "BAIXADO"
    assert linha["assunto"].startswith("1) DIREITO PENAL MILITAR,CRIMES CONTRA INCOLUMIDADE PÚBLICA")
    assert linha["url_processo"] == (
        "https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=processo_seleciona_publica"
        "&acao_origem=busca_processos&num_processo=70003740620207000000"
    )
    assert [parte["tipo"] for parte in linha["partes"]] == ["Mp", "Paciente"]
    assert linha["partes"][0] == {"tipo": "Mp", "nome": "MINISTÉRIO PÚBLICO MILITAR", "qualificacao": None}
    assert linha["partes"][1]["qualificacao"] == "SOLDADO / EXÉRCITO"
    assert [rep["tipo"] for rep in linha["representantes"]] == ["Procurador", "Procurador"]
    assert linha["representantes"][1]["partes"] == ["MINISTÉRIO PÚBLICO MILITAR"]


@responses.activate
def test_filtros_sem_pesquisa_vao_pela_pesquisa_avancada(mocker):
    """Sem número, o portal lista o que os filtros selecionam; o sample traz um processo de Auditoria."""
    mocker.patch("time.sleep")
    _add_page("processos/filtro_situacao.html", assunto="INCITAMENTO", situacao="MOVIMENTO")

    df = jus.scraper("stm").listar_processos(assunto="INCITAMENTO", situacao="MOVIMENTO")

    assert responses.calls[0].request.params == {
        "search_filter_option": "feitos",
        "search_filter": "busca_avancada",
        "q": "",
        "q_or": "",
        "start": "0",
        "rows": "100",
        "fq_assunto_pesquisa": "INCITAMENTO",
        "fq_situacao": "MOVIMENTO",
    }
    assert len(df) == 2
    assert set(df["situacao"]) == {"MOVIMENTO"}
    assert df["assunto"].str.contains("INCITAMENTO").all()
    assert df["data_autuacao"].is_monotonic_decreasing
    da_auditoria = df[df["juiz"].notna()].iloc[0]
    assert da_auditoria["orgao"].startswith("AUDITORIA DA 4ª CJM")
    assert da_auditoria["conselho"] == "CONSELHO ESPECIAL DE JUSTIÇA - EXÉRCITO"
    assert pd.isna(da_auditoria["relator"])


@responses.activate
def test_processos_fisicos_sem_data_nem_link(mocker):
    """Processo antigo, em papel: o portal não publica a autuação nem o endereço no eproc."""
    mocker.patch("time.sleep")
    _add_page("processos/processos_fisicos.html", "0000028-58.2008.7.01.0101")

    df = jus.scraper("stm").listar_processos("0000028-58.2008.7.01.0101")

    assert len(df) == 3
    assert df["processo"].notna().all()
    assert df["data_autuacao"].notna().sum() == 1
    assert df["url_processo"].notna().sum() == 1
    assert df["partes"].map(len).tolist() == [3, 1, 1]
    assert df["representantes"].map(len).tolist() == [6, 0, 1]


@responses.activate
def test_todos_os_filtros_e_a_pagina_chegam_na_query(mocker):
    mocker.patch("time.sleep")
    responses.add(responses.GET, BASE_URL, body=load_sample("stm", "processos/por_numero.html"))

    jus.scraper("stm").listar_processos(
        " 7000374- ",
        paginas=[1],
        cjm="11ª CIRCUNSCRIÇÃO JUDICIÁRIA MILITAR - DF",
        orgao="SUPERIOR TRIBUNAL MILITAR",
        conselho="CONSELHO PERMANENTE DE JUSTIÇA - EXÉRCITO",
        situacao="BAIXADO",
        classe="HABEAS CORPUS CRIMINAL",
        assunto="PECULATO",
    )

    assert responses.calls[0].request.params == {
        "search_filter_option": "feitos",
        "search_filter": "numero",
        "search_input": "7000374-",
        "q": "7000374-",
        "q_or": "7000374-",
        "start": "0",
        "rows": "100",
        "fq_cjm": "11ª CIRCUNSCRIÇÃO JUDICIÁRIA MILITAR - DF",
        "fq_orgao": "SUPERIOR TRIBUNAL MILITAR",
        "fq_conselho": "CONSELHO PERMANENTE DE JUSTIÇA - EXÉRCITO",
        "fq_situacao": "BAIXADO",
        "fq_classe": "HABEAS CORPUS CRIMINAL",
        "fq_assunto_pesquisa": "PECULATO",
    }


def test_pagina_seguinte_pede_o_start_da_pagina():
    assert build_processos_params("", 3, orgao="SUPERIOR TRIBUNAL MILITAR")["start"] == "200"


@pytest.mark.parametrize("pesquisa", [None, "", "  "])
def test_sem_pesquisa_nem_filtro_levanta(pesquisa):
    with pytest.raises(ValueError, match="precisa de 'pesquisa'"):
        jus.scraper("stm").listar_processos(pesquisa)


def test_kwarg_desconhecido_levanta_type_error():
    assert_unknown_kwarg_raises(jus.scraper("stm").listar_processos, "parametro_bobo", "7000374-06.2020.7.00.0000")


@responses.activate
def test_sem_resultados(mocker):
    """Busca vazia: o portal redireciona para ``index.php``, que mostra o aviso (sample do cjsg)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        BASE_URL,
        status=302,
        headers={"Location": f"{INDEX_URL}?search_filter_option=feitos&search_filter=numero"},
    )
    responses.add(responses.GET, INDEX_URL, body=load_sample("stm", "cjsg/no_results.html"))

    df = jus.scraper("stm").listar_processos("0000000-00.0000.0.00.0000")

    assert df.empty
    assert list(df.columns) == COLUNAS_PROCESSOS


@responses.activate
def test_bloqueio_do_waf_levanta():
    responses.add(responses.GET, BASE_URL, body=load_sample("stm", "cjsg/waf_rejected.html"))

    with pytest.raises(BotChallengeBlockedError, match="Request Rejected"):
        jus.scraper("stm").listar_processos("7000374-06.2020.7.00.0000")


@responses.activate
def test_download_e_parse_separados(mocker):
    mocker.patch("time.sleep")
    _add_page("processos/por_numero.html", "7000374-06.2020.7.00.0000")
    stm = jus.scraper("stm")

    brutos = stm.listar_processos_download("7000374-06.2020.7.00.0000")

    assert len(brutos) == 1
    assert stm.listar_processos_parse(brutos)["processo"].tolist() == ["7000374-06.2020.7.00.0000"]
