"""Offline contract tests for TJSP cpopg (``method='html'``).

Mocks the request flows against samples captured by
``tests/fixtures/capture/tjsp.py``. Validates that the public ``.cpopg()``
call returns a dict of DataFrames with the expected keys and minimum
schema.

HTML flow: GET ``cpopg/search.do?…`` → scraper extracts one
``processo.codigo`` → saves the search response itself (the eSAJ returns
the process details directly when the CNJ is unique).
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import requests
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"

CPOPG_HTML_KEYS = {"basicos", "partes", "movimentacoes", "peticoes_diversas"}
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


# ---------- method='html': processo que falha não some (#460) ------------

# Número sem processo no TJSP; a busca responde "Não existem informações
# disponíveis para os parâmetros informados." (captura de 15/11/2026).
CNJ_INEXISTENTE = "0000001-12.2024.8.26.0100"
CNJ_SEM_CONEXAO = "1000000-00.2024.8.26.0001"


def _registrar_busca_por_cnj(cnj, **resposta):
    responses.add(
        responses.GET,
        f"{ESAJ}/cpopg/search.do",
        match=[query_param_matcher({"dadosConsulta.valorConsultaNuUnificado": cnj}, strict_match=False)],
        **resposta,
    )


@responses.activate
def test_cpopg_html_todo_cnj_pedido_sai_em_basicos_com_motivo_falha(tmp_path, mocker):
    """O processo que não foi baixado fica em ``basicos``, com o motivo, e o aviso o nomeia.

    Antes, o CNJ que falhava saía só no log, e o inexistente era tratado
    como falha depois de cinco tentativas.
    """
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(
        CNJ, body=load_sample_bytes("tjsp", "cpopg/search.html"), content_type="text/html; charset=utf-8",
    )
    _registrar_busca_por_cnj(
        CNJ_INEXISTENTE, body=load_sample_bytes("tjsp", "cpopg/search_sem_informacoes.html"),
        content_type="text/html;charset=UTF-8",
    )
    _registrar_busca_por_cnj(CNJ_SEM_CONEXAO, body=requests.ConnectionError("recusada"))

    with pytest.warns(
        UserWarning,
        match=rf"TJSPScraper\.cpopg: 2 consulta\(s\) de processo falharam\. Falhas: {CNJ_INEXISTENTE}: nao_encontrado; "
        rf"{CNJ_SEM_CONEXAO}: conexao\..*segredo de justiça",
    ):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg([CNJ, CNJ_INEXISTENTE, CNJ_SEM_CONEXAO])

    basicos = result["basicos"]
    assert basicos[["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ, "motivo_falha": None},
        {"id_processo": CNJ_INEXISTENTE, "motivo_falha": "nao_encontrado"},
        {"id_processo": CNJ_SEM_CONEXAO, "motivo_falha": "conexao"},
    ]
    assert basicos.iloc[0]["classe"] is not None
    assert basicos.iloc[1:].drop(columns=["id_processo", "motivo_falha"]).isna().all().all()
    assert set(result["partes"]["file_path"]) == {basicos.iloc[0]["file_path"]}
    buscas = [c.request.params["dadosConsulta.valorConsultaNuUnificado"] for c in responses.calls]
    assert buscas.count(CNJ_INEXISTENTE) == 1
    assert buscas.count(CNJ_SEM_CONEXAO) == 5


@responses.activate
def test_cpopg_html_lote_sem_nenhum_processo_baixado_devolve_as_linhas_de_falha(tmp_path, mocker):
    """Sem arquivo para ler, ``cpopg`` devolve as tabelas vazias e as linhas de falha, sem erro de leitura."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(
        CNJ_INEXISTENTE, body=load_sample_bytes("tjsp", "cpopg/search_sem_informacoes.html"),
        content_type="text/html;charset=UTF-8",
    )

    with pytest.warns(UserWarning, match=f"{CNJ_INEXISTENTE}: nao_encontrado"):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg([CNJ_INEXISTENTE, "123"])

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ_INEXISTENTE, "motivo_falha": "nao_encontrado"},
        {"id_processo": "123", "motivo_falha": "entrada_invalida"},
    ]
    assert {"classe", "situacao"} <= set(result["basicos"].columns)
    assert all(result[tabela].empty for tabela in ("partes", "movimentacoes", "peticoes_diversas"))
    assert len(responses.calls) == 1


@responses.activate
def test_cpopg_html_busca_com_status_de_erro_sai_com_o_status(tmp_path, mocker):
    """A página de erro da busca não é lida como "nenhum link": o processo sai com ``http_<status>``."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ, status=503, body="<html>Serviço indisponível</html>")

    with pytest.warns(UserWarning, match=f"{CNJ}: http_503"):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ)

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ, "motivo_falha": "http_503"},
    ]
    assert len(responses.calls) == 5


def test_cpopg_lote_so_com_entrada_invalida_nao_deixa_pasta(tmp_path):
    """Sem nenhuma requisição, ``cpopg`` devolve as linhas sem erro e não deixa a pasta de download."""
    pasta = tmp_path / "nao_criada"

    with pytest.warns(UserWarning, match="123: entrada_invalida"):
        result = jus.scraper("tjsp", download_path=str(pasta)).cpopg(["123", float("nan")])

    assert result["basicos"]["motivo_falha"].tolist() == ["entrada_invalida", "entrada_invalida"]
    assert result["basicos"]["id_processo"].iloc[0] == "123"
    assert not pasta.exists()


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
    """Cursor repetido não avança a paginação: o processo fica sem arquivo, com o motivo no retorno e no aviso."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    pagina_2 = load_sample("tjsp", "cpopg/movimentacoes_pagina_2.html").replace(CURSOR_PAGINA_3, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2, body=pagina_2)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    erro = mocker.patch("juscraper.courts.tjsp.cpopg_download.logger.error")

    with pytest.warns(UserWarning, match=f"{CNJ_INCIDENTE}: resposta_inesperada"):
        falhas = scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert falhas == {CNJ_INCIDENTE: "resposta_inesperada"}

    assert len(_chamadas("carregarMovimentacoesAjax.do")) == 2
    assert "a paginação não avançaria" in str(erro.call_args.args[-1])
    assert not list((tmp_path / "cpopg").rglob("*.html"))


@responses.activate
def test_cpopg_html_para_quando_a_pagina_se_repete_com_cursor_novo(tmp_path, mocker):
    """Página igual à anterior, com cursor novo, não avança a paginação: o processo fica sem arquivo, com o motivo.

    Em 02/11/2026 o eSAJ chegou a devolver a mesma página com um cursor novo a
    cada chamada (#474); sem a checagem, o download seguiria sem fim.
    """
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    pagina_2 = load_sample_bytes("tjsp", "cpopg/movimentacoes_pagina_2.html")
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_3, body=pagina_2.replace(CURSOR_PAGINA_3.encode(), b"cursor-novo"))
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    erro = mocker.patch("juscraper.courts.tjsp.cpopg_download.logger.error")

    with pytest.warns(UserWarning, match=f"{CNJ_INCIDENTE}: resposta_inesperada"):
        falhas = scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert falhas == {CNJ_INCIDENTE: "resposta_inesperada"}

    assert len(_chamadas("carregarMovimentacoesAjax.do")) == 3
    assert "repetiu a página anterior" in str(erro.call_args.args[-1])
    assert not list((tmp_path / "cpopg").rglob("*.html"))


@responses.activate
def test_cpopg_html_para_quando_a_pagina_seguinte_vem_sem_linhas(tmp_path, mocker):
    """Página seguinte sem movimentações não avança a paginação: o processo fica sem arquivo, com o motivo."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2, body="")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    erro = mocker.patch("juscraper.courts.tjsp.cpopg_download.logger.error")

    with pytest.warns(UserWarning, match=f"{CNJ_INCIDENTE}: resposta_inesperada"):
        falhas = scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert falhas == {CNJ_INCIDENTE: "resposta_inesperada"}

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


@responses.activate
def test_cpopg_html_sem_movimentacoes_nao_chama_o_ajax(tmp_path, mocker):
    """Com ``baixar_movimentacoes=False`` não há requisição de movimentações nem aviso."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(
        CNJ_INCIDENTE, method="html", baixar_movimentacoes=False,
    )

    assert not _chamadas("carregarMovimentacoesAjax.do")
    assert result["movimentacoes"].empty
    assert result["basicos"].iloc[0]["situacao"] == "Extinto"


@responses.activate
@pytest.mark.parametrize("anterior", ["sem_movimentacoes", "versao_antiga"])
def test_cpopg_download_com_movimentacoes_baixa_de_novo_o_salvo_sem_elas(tmp_path, mocker, anterior):
    """HTML salvo sem as movimentações não conta como baixado quando o download as pede."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    if anterior == "sem_movimentacoes":
        _registrar_busca_incidente()
        scraper.cpopg_download(CNJ_INCIDENTE, method="html", baixar_movimentacoes=False)
    else:
        pasta = tmp_path / "cpopg" / CNJ_INCIDENTE.replace("-", "").replace(".", "")
        pasta.mkdir(parents=True)
        (pasta / f"{pasta.name}_{CD_INCIDENTE}.html").write_bytes(
            load_sample_bytes("tjsp", "cpopg/show_incidente.html"),
        )
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)

    scraper.cpopg_download(CNJ_INCIDENTE, method="html")

    assert len(_chamadas("carregarMovimentacoesAjax.do")) == 3
    assert len(scraper.cpopg_parse(str(tmp_path / "cpopg"))["movimentacoes"]) == 14


@responses.activate
@pytest.mark.parametrize(("primeiro", "segundo"), [(True, True), (True, False), (False, False)])
def test_cpopg_download_pula_o_processo_ja_salvo(tmp_path, mocker, primeiro, segundo):
    """Só o arquivo sem movimentações, num download que as pede, é baixado de novo."""
    mocker.patch("time.sleep")
    _registrar_busca_incidente()
    _registrar_pagina_movimentacoes(1)
    _registrar_pagina_movimentacoes(2, CURSOR_PAGINA_2)
    _registrar_pagina_movimentacoes(3, CURSOR_PAGINA_3)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cpopg_download(CNJ_INCIDENTE, method="html", baixar_movimentacoes=primeiro)
    scraper.cpopg_download(CNJ_INCIDENTE, method="html", baixar_movimentacoes=segundo)

    assert len(_chamadas("search.do")) == 1


# ---------- method='api': removido ----------------------------------------

@pytest.mark.parametrize("metodo", ["cpopg", "cpopg_download", "cposg", "cposg_download"])
@responses.activate
def test_method_api_removido_levanta_erro_sem_rede(tmp_path, metodo):
    """``method='api'`` levanta ``ValueError`` explicando a remoção, antes de qualquer requisição."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match="method='api' foi removido"):
        getattr(scraper, metodo)(CNJ, method="api")

    assert not responses.calls


def _pasta_da_chamada_fixa(tmp_path, mocker):
    """A pasta que o composto cria para a chamada, já existente, para o teste pôr arquivos nela."""
    pasta = tmp_path / "composto_fixo"
    pasta.mkdir()
    mocker.patch("juscraper.courts.tjsp.client.tempfile.mkdtemp", return_value=str(pasta))
    return pasta


@responses.activate
def test_cpopg_falhas_de_download_e_de_leitura_saem_num_unico_aviso(tmp_path, mocker):
    """Lote com falha de download e de leitura avisa uma vez, com as duas, como o composto do TRF.

    Antes, saíam dois avisos: o do download e o do parse.
    """
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ_SEM_CONEXAO, body=requests.ConnectionError("recusada"))
    # Processos já na pasta da chamada: um legível e um que o parse recusa.
    pasta = _pasta_da_chamada_fixa(tmp_path, mocker)
    legivel = pasta / "cpopg" / "10093677620178260344"
    legivel.mkdir(parents=True)
    (legivel / "show_standard.html").write_text(load_sample("tjsp", "cpopg/show_standard.html"), encoding="utf-8")
    ilegivel = pasta / "cpopg" / "10001497120248260346"
    ilegivel.mkdir()
    (ilegivel / "quebrado.html").write_bytes(b"\xff\xfe\xfa invalido em utf-8")

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        # Sem movimentações, os dois processos salvos contam como baixados e não são pedidos de novo.
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(
            ["1009367-76.2017.8.26.0344", CNJ, CNJ_SEM_CONEXAO], baixar_movimentacoes=False,
        )

    assert len(avisos) == 1
    mensagem = str(avisos[0].message)
    assert mensagem.startswith(
        "TJSPScraper.cpopg: 2 consulta(s) de processo ou leitura(s) de arquivo falharam. "
        f"Falhas: {CNJ_SEM_CONEXAO}: conexao; "
    )
    assert "quebrado.html: resposta_inesperada" in mensagem
    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": "1009367-76.2017.8.26.0344", "motivo_falha": None},
        {"id_processo": CNJ, "motivo_falha": "resposta_inesperada"},
        {"id_processo": CNJ_SEM_CONEXAO, "motivo_falha": "conexao"},
    ]


@responses.activate
def test_cpopg_le_so_os_processos_do_lote(tmp_path, mocker):
    """Processo e falha de um ``cpopg_download`` anterior na mesma pasta ficam fora do composto.

    Antes, o ``cpopg`` lia a pasta de download inteira: o lote de um CNJ
    devolvia também o processo salvo antes e a falha registrada antes.
    """
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ_INEXISTENTE, body=requests.ConnectionError("recusada"))
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(UserWarning, match=f"{CNJ_INEXISTENTE}: conexao"):
        scraper.cpopg_download(CNJ_INEXISTENTE)
    anterior = tmp_path / "cpopg" / "10093677620178260344"
    anterior.mkdir(parents=True)
    (anterior / "show_standard.html").write_text(load_sample("tjsp", "cpopg/show_standard.html"), encoding="utf-8")
    # A página de 2º grau do mesmo CNJ, de um cposg_download na mesma pasta, também fica de fora.
    segundo_grau = tmp_path / "cposg" / "10001497120248260346"
    segundo_grau.mkdir(parents=True)
    (segundo_grau / "show.html").write_text(load_sample("tjsp", "cposg/show.html"), encoding="utf-8")
    _registrar_busca_por_cnj(
        CNJ, body=load_sample_bytes("tjsp", "cpopg/search.html"), content_type="text/html; charset=utf-8",
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = scraper.cpopg(CNJ, baixar_movimentacoes=False)

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ, "motivo_falha": None},
    ]


@responses.activate
def test_cpopg_arquivos_ilegiveis_com_falha_de_download_devolvem_as_linhas(tmp_path, mocker):
    """Antes, o lote em que todo arquivo é ilegível levantava ``ValueError`` mesmo com falha de download."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ_SEM_CONEXAO, body=requests.ConnectionError("recusada"))
    ilegivel = _pasta_da_chamada_fixa(tmp_path, mocker) / "cpopg" / "10001497120248260346"
    ilegivel.mkdir(parents=True)
    (ilegivel / "quebrado.html").write_bytes(b"\xff\xfe\xfa invalido em utf-8")

    with pytest.warns(UserWarning, match=rf"{CNJ_SEM_CONEXAO}: conexao; .*quebrado\.html: resposta_inesperada"):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(
            [CNJ, CNJ_SEM_CONEXAO], baixar_movimentacoes=False,
        )

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ, "motivo_falha": "resposta_inesperada"},
        {"id_processo": CNJ_SEM_CONEXAO, "motivo_falha": "conexao"},
    ]
    assert all(result[tabela].empty for tabela in ("partes", "movimentacoes", "peticoes_diversas"))


@responses.activate
def test_cpopg_parse_devolve_o_processo_que_o_download_nao_baixou(tmp_path, mocker):
    """No fluxo em duas etapas, o CNJ que o download não baixou sai em ``basicos``, como no ``cpopg``."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(
        CNJ, body=load_sample_bytes("tjsp", "cpopg/search.html"), content_type="text/html; charset=utf-8",
    )
    _registrar_busca_por_cnj(CNJ_SEM_CONEXAO, body=requests.ConnectionError("recusada"))
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=rf"cpopg_download: .*{CNJ_SEM_CONEXAO}: conexao.*cpopg_parse os devolve"):
        scraper.cpopg_download([CNJ, CNJ_SEM_CONEXAO, "123"])
    with pytest.warns(UserWarning, match=rf"cpopg_parse: 2 consulta\(s\) de processo falharam.*{CNJ_SEM_CONEXAO}"):
        result = scraper.cpopg_parse(str(tmp_path))

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": CNJ, "motivo_falha": None},
        {"id_processo": CNJ_SEM_CONEXAO, "motivo_falha": "conexao"},
        {"id_processo": "123", "motivo_falha": "entrada_invalida"},
    ]


@responses.activate
def test_cpopg_download_que_passa_depois_tira_a_falha_anterior(tmp_path, mocker):
    """O CNJ que falhou e foi baixado depois, na mesma pasta, não sai mais como falha no parse."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ, body=requests.ConnectionError("recusada"))
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(UserWarning, match=f"{CNJ}: conexao"):
        scraper.cpopg_download(CNJ)
    with pytest.warns(UserWarning, match=f"{CNJ}: conexao"):
        assert scraper.cpopg_parse(str(tmp_path))["basicos"]["motivo_falha"].tolist() == ["conexao"]

    responses.replace(
        responses.GET, f"{ESAJ}/cpopg/search.do",
        body=load_sample_bytes("tjsp", "cpopg/search.html"), content_type="text/html; charset=utf-8",
    )
    scraper.cpopg_download(CNJ)

    basicos = scraper.cpopg_parse(str(tmp_path))["basicos"]
    assert basicos[["id_processo", "motivo_falha"]].to_dict("records") == [{"id_processo": CNJ, "motivo_falha": None}]
    assert not (tmp_path / "cpopg" / "falhas_download.json").exists()


def test_cpopg_lote_vazio_devolve_as_tabelas_vazias(tmp_path):
    """``cpopg([])`` devolve as quatro tabelas vazias, com ``motivo_falha`` em ``basicos``, sem erro de leitura."""
    result = jus.scraper("tjsp", download_path=str(tmp_path / "x")).cpopg([])

    assert all(tabela.empty for tabela in result.values())
    assert "motivo_falha" in result["basicos"].columns


def test_cpopg_entrada_que_nao_e_texto_vira_linha_de_falha(tmp_path):
    """Número de uma coluna numérica (``numpy.int64``) e ``None`` saem ``entrada_invalida``, sem quebrar o registro."""
    with pytest.warns(UserWarning, match="entrada_invalida"):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg([np.int64(123), None])

    assert result["basicos"][["id_processo", "motivo_falha"]].to_dict("records") == [
        {"id_processo": "123", "motivo_falha": "entrada_invalida"},
        {"id_processo": "None", "motivo_falha": "entrada_invalida"},
    ]


@pytest.mark.parametrize("metodo", ["cpopg_download", "cposg_download"])
def test_download_devolve_chave_str_para_entrada_que_nao_e_texto(tmp_path, metodo):
    """As falhas saem com chave ``str``, a mesma que ``*_parse`` devolve em ``id_processo``."""
    with pytest.warns(UserWarning, match="entrada_invalida"):
        falhas = getattr(jus.scraper("tjsp", download_path=str(tmp_path)), metodo)([np.int64(123), None])

    assert falhas == {"123": "entrada_invalida", "None": "entrada_invalida"}


def _arquivos_alheios(pasta):
    """Um download anterior do mesmo CNJ e um arquivo do usuário, que ``cpopg`` não pode apagar."""
    anterior = pasta / "cpopg" / "10001497120248260346" / "10001497120248260346_ANTIGO.html"
    anterior.parent.mkdir(parents=True)
    anterior.write_text("download anterior", encoding="utf-8")
    proprio = pasta / "planilha.csv"
    proprio.write_text("a,b\n", encoding="utf-8")
    return {anterior: "download anterior", proprio: "a,b\n"}


def _pastas_da_chamada(pasta):
    return [p for p in pasta.iterdir() if p.is_dir() and p.name != "cpopg"]


@responses.activate
def test_cpopg_preserva_arquivos_que_ja_estavam_em_download_path(tmp_path, mocker):
    """``cpopg`` baixa numa pasta própria e apaga só ela; antes, apagava ``download_path`` inteiro."""
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(
        CNJ, body=load_sample_bytes("tjsp", "cpopg/search.html"), content_type="text/html; charset=utf-8",
    )
    alheios = _arquivos_alheios(tmp_path)

    result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ)

    assert result["basicos"]["motivo_falha"].tolist() == [None]
    assert result["basicos"]["classe"].notna().all()
    assert {caminho: caminho.read_text(encoding="utf-8") for caminho in alheios} == alheios
    assert _pastas_da_chamada(tmp_path) == []


@responses.activate
def test_cpopg_com_falha_preserva_arquivos_que_ja_estavam_em_download_path(tmp_path, mocker):
    mocker.patch("time.sleep")
    _registrar_busca_por_cnj(CNJ, status=503, body="<html>Serviço indisponível</html>")
    alheios = _arquivos_alheios(tmp_path)

    with pytest.warns(UserWarning, match=f"{CNJ}: http_503"):
        result = jus.scraper("tjsp", download_path=str(tmp_path)).cpopg(CNJ)

    assert result["basicos"]["motivo_falha"].tolist() == ["http_503"]
    assert {caminho: caminho.read_text(encoding="utf-8") for caminho in alheios} == alheios
    assert _pastas_da_chamada(tmp_path) == []


@pytest.mark.parametrize("metodo", ["cpopg", "cposg"])
def test_composto_apaga_raiz_temporaria_criada_pelo_scraper(metodo):
    """Sem caminho explícito, o composto limpa também a raiz que a propriedade criou."""
    scraper = jus.scraper("tjsp")

    with pytest.warns(UserWarning, match="entrada_invalida"):
        getattr(scraper, metodo)([None])

    assert not Path(scraper.download_path).exists()


@pytest.mark.parametrize("ids", [[None], []], ids=["falha_por_linha", "lote_vazio"])
def test_cpopg_com_diretorio_apaga_raiz_temporaria_criada_na_validacao(tmp_path, ids):
    """A checagem de ``diretorio`` lê ``download_path`` antes de iniciar o lote."""
    scraper = jus.scraper("tjsp")
    kwargs = {"baixar_movimentacoes": True, "download_pecas": True, "diretorio": str(tmp_path / "pecas")}

    if ids:
        with pytest.warns(UserWarning, match="entrada_invalida"):
            scraper.cpopg(ids, **kwargs)
    else:
        scraper.cpopg(ids, **kwargs)

    assert not Path(scraper.download_path).exists()
