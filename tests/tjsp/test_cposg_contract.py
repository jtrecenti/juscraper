"""Offline contract tests for TJSP cposg (``method='html'``).

HTML flow: GET ``cposg/open.do`` → GET ``cposg/search.do`` → Caso 3
(resposta simples) or Caso 1/2 (listagem/modal). The CNJ used here lands
in Caso 3 — the search response itself contains the process details and
the scraper saves it under the ``cdProcesso`` value. The page leaves the
movements to ``carregarMovimentacoesAjax.do`` (five rows per page, next page
by ``cursor``), which the scraper follows and writes into the saved HTML.
"""
import warnings

import pandas as pd
import pytest
import requests
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts._esaj.acordao import parse_cursor
from tests._helpers import load_sample, load_sample_bytes, rotas_enviadas, timeout_enviado, url_enviada

ESAJ = "https://esaj.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"

CPOSG_BASICOS_MIN = {"id_original", "classe", "status"}

# Ordem pública das colunas do cposg HTML. A lista é literal de propósito: se o
# teste importasse a constante do módulo testado, uma reordenação dela passaria.
CPOSG_COLUNAS_ORDENADAS = [
    "id_original", "processo", "status", "classe", "assunto", "secao",
    "orgao_julgador", "area", "relator", "valor_da_acao", "origem",
    "volume_apenso", "movimentacoes", "partes", "historico", "decisoes",
    "composicao", "primeira_inst", "motivo_falha",
]

CD_PROCESSO = "RI008L7SC0000"
PAGINAS_MOVIMENTACOES = 5


def _registrar_busca():
    """``open.do`` e ``search.do`` gravados; a busca devolve a página do processo."""
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/open.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"gateway": "true"})],
    )
    search_params = {
        "conversationId": "",
        "paginaConsulta": "1",
        "localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMPROC",
        "tipoNuProcesso": "UNIFICADO",
        "numeroDigitoAnoUnificado": "1000149-71.2024",
        "foroNumeroUnificado": "0346",
        "dePesquisaNuUnificado": CNJ,
        "dePesquisa": "",
        "uuidCaptcha": "",
        "pbEnviar": "Pesquisar",
    }
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/search_listagem.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(search_params)],
    )


def _registrar_movimentacoes():
    """Páginas gravadas do ``carregarMovimentacoesAjax.do``; a ``n`` casa com o cursor da ``n - 1``."""
    params = {"cdProcesso": CD_PROCESSO}
    for numero in range(1, PAGINAS_MOVIMENTACOES + 1):
        corpo = load_sample("tjsp", f"cposg/movimentacoes_pagina_{numero}.html")
        responses.add(
            responses.GET,
            f"{ESAJ}/cposg/carregarMovimentacoesAjax.do",
            body=corpo,
            status=200,
            content_type="text/html;charset=UTF-8",
            match=[query_param_matcher(params)],
        )
        params = {"cdProcesso": CD_PROCESSO, "cursor": parse_cursor(corpo) or ""}


CNJ_SEM_INFORMACOES = "0003941-71.2024.8.26.0048"


def _registrar_busca_sem_informacoes():
    """``search.do`` do número que o 2º grau não tem: "Não existem informações disponíveis"."""
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/search_sem_informacoes.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"dePesquisaNuUnificado": CNJ_SEM_INFORMACOES}, strict_match=False)],
    )


# ---------- method='html' -----------------------------------------------

@responses.activate
def test_cposg_html_simple_response(tmp_path, mocker):
    """HTML flow — Caso 3 (resposta simples), com as movimentações das cinco páginas AJAX."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert set(df.columns) >= CPOSG_BASICOS_MIN
    assert list(df.columns) == CPOSG_COLUNAS_ORDENADAS
    row = df.iloc[0]
    assert row["classe"] == "Apelação Cível"
    assert row["relator"] is not None
    movimentacoes = row["movimentacoes"]
    assert len(movimentacoes) == 24
    assert movimentacoes[:2] == [
        {
            "data": "25/06/2025",
            "movimento": "Expedido Certidão de Baixa de Recurso",
            "descricao": "Certidão de Baixa de Recurso - [Digital]",
        },
        {"data": "25/06/2025", "movimento": "Baixa Definitiva", "descricao": ""},
    ]
    datas = [mov["data"] for mov in movimentacoes]
    assert datas[-1] == "05/02/2025"
    assert len(set(map(str, movimentacoes))) == len(movimentacoes)


@responses.activate
def test_cposg_html_movimentacoes_fora_do_formato_falha_alto(tmp_path, mocker, caplog):
    """Sem a sessão do processo, o eSAJ devolve a página sem a tabela: nada é gravado, e o CNJ sai com o motivo."""
    mocker.patch("time.sleep")
    _registrar_busca()
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/carregarMovimentacoesAjax.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html;charset=UTF-8",
    )

    with pytest.warns(
        UserWarning, match=rf"TJSPScraper\.cposg: 1 consulta\(s\) de processo falharam.*{CNJ}: resposta_inesperada",
    ):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": "resposta_inesperada"},
    ]
    assert list(df.columns) == CPOSG_COLUNAS_ORDENADAS
    assert "a primeira página veio fora do formato conhecido" in caplog.text


@responses.activate
def test_cposg_html_pagina_seguinte_fora_do_formato_nao_corta_a_lista(tmp_path, mocker, caplog):
    """Página 2 sem a linha de metadados (sessão perdida) não encerra a lista em silêncio."""
    mocker.patch("time.sleep")
    _registrar_busca()
    primeira = load_sample("tjsp", "cposg/movimentacoes_pagina_1.html")
    url = f"{ESAJ}/cposg/carregarMovimentacoesAjax.do"
    responses.add(responses.GET, url, body=primeira, match=[query_param_matcher({"cdProcesso": CD_PROCESSO})])
    responses.add(
        responses.GET, url, body=load_sample_bytes("tjsp", "cposg/open.html"),
        match=[query_param_matcher({"cdProcesso": CD_PROCESSO, "cursor": parse_cursor(primeira) or ""})],
    )

    with pytest.warns(UserWarning, match=f"{CNJ}: resposta_inesperada"):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

    assert df["motivo_falha"].tolist() == ["resposta_inesperada"]
    assert "a página 2 veio fora do formato conhecido" in caplog.text


@responses.activate
def test_cposg_download_html_usa_diretorio_sem_alterar_download_path(tmp_path, mocker):
    """O destino alternativo do HTML não deve alterar o destino configurado."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    caminho = tmp_path / "padrao"
    alternativo = tmp_path / "alternativo"
    scraper = jus.scraper("tjsp", download_path=str(caminho))

    scraper.cposg_download(CNJ, method="html", diretorio=str(alternativo))

    assert (alternativo / "cposg").is_dir()
    assert not (caminho / "cposg").exists()
    assert scraper.download_path == str(caminho)


@responses.activate
def test_cposg_processo_sem_informacoes_sai_como_nao_encontrado(tmp_path, mocker):
    """O número que o 2º grau não tem sai numa linha ``nao_encontrado``, e o aviso o nomeia."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    _registrar_busca_sem_informacoes()

    with pytest.warns(UserWarning, match=f"{CNJ_SEM_INFORMACOES}: nao_encontrado.*segredo de justiça"):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg([CNJ_SEM_INFORMACOES, CNJ])

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": None},
        {"processo": CNJ_SEM_INFORMACOES, "motivo_falha": "nao_encontrado"},
    ]
    assert df["classe"].iloc[0] is not None


@responses.activate
def test_cposg_so_processo_sem_informacoes_avisa_e_devolve_a_linha(tmp_path, mocker):
    """Só o número sem informações: uma linha ``nao_encontrado``, com as colunas de sempre."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_busca_sem_informacoes()

    with pytest.warns(UserWarning, match=CNJ_SEM_INFORMACOES):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ_SEM_INFORMACOES)

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ_SEM_INFORMACOES, "motivo_falha": "nao_encontrado"},
    ]
    assert list(df.columns) == CPOSG_COLUNAS_ORDENADAS


@responses.activate
def test_cposg_so_processo_sem_informacoes_nao_le_o_cpopg(tmp_path, mocker):
    """Com o ``cpopg/`` no mesmo ``download_path``, o número sem informações não traz processo de 1º grau.

    O parse devolve só a linha do número, com o motivo que o download gravou.
    """
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_busca_sem_informacoes()
    cpopg = tmp_path / "cpopg" / "10001497120248260346"
    cpopg.mkdir(parents=True)
    (cpopg / "10001497120248260346.html").write_bytes(load_sample_bytes("tjsp", "cposg/show_com_incidentes.html"))
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=CNJ_SEM_INFORMACOES):
        scraper.cposg_download(CNJ_SEM_INFORMACOES)
    with pytest.warns(UserWarning, match=f"cposg_parse: .*{CNJ_SEM_INFORMACOES}: nao_encontrado"):
        df = scraper.cposg_parse(str(tmp_path))

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ_SEM_INFORMACOES, "motivo_falha": "nao_encontrado"},
    ]


@responses.activate
def test_cposg_outra_mensagem_do_esaj_nao_vira_processo(tmp_path, mocker, caplog):
    """Mensagem de erro do eSAJ na busca não é gravada como processo: o download falha e diz qual foi."""
    mocker.patch("time.sleep")
    _registrar_busca()
    responses.replace(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/show.html"),
        status=200,
        content_type="text/html; charset=utf-8",
    )

    with pytest.warns(UserWarning, match=f"{CNJ}: resposta_inesperada"):
        falhas = jus.scraper("tjsp", download_path=str(tmp_path)).cposg_download(CNJ)

    assert falhas == {CNJ: "resposta_inesperada"}
    assert "Não foi possível executar esta operação" in caplog.text
    assert not list(tmp_path.rglob("*.html"))


@responses.activate
def test_todo_pedido_do_cposg_tem_timeout(tmp_path, mocker):
    """open.do, busca, show.do (listagem e incidentes) e movimentações saem com prazo (#484)."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    cnj_listagem, cnj_incidentes = "0000001-00.2024.8.26.0001", "0000002-00.2024.8.26.0001"
    respostas_da_busca = {
        cnj_listagem: (
            '<div id="listagemDeProcessos"><a class="linkProcesso" href="/cposg/show.do?processo.codigo=L1">x</a></div>'
        ),
        cnj_incidentes: '<div id="modalIncidentes"><input id="processoSelecionado" value="I1"></div>',
    }
    for cnj, corpo in respostas_da_busca.items():
        responses.add(
            responses.GET,
            f"{ESAJ}/cposg/search.do",
            body=corpo,
            content_type="text/html; charset=utf-8",
            match=[query_param_matcher({"dePesquisaNuUnificado": cnj}, strict_match=False)],
        )
    responses.add(responses.GET, f"{ESAJ}/cposg/show.do", body="<html>processo</html>", content_type="text/html")

    jus.scraper("tjsp", download_path=str(tmp_path)).cposg_download([CNJ, cnj_listagem, cnj_incidentes])

    rotas = rotas_enviadas()
    assert set(rotas) == {"open.do", "search.do", "show.do", "carregarMovimentacoesAjax.do"}
    assert rotas.count("show.do") == 2
    sem_timeout = [url_enviada(c.request) for c in responses.calls if timeout_enviado(c.request) is None]
    assert sem_timeout == []


@responses.activate
def test_cposg_processo_que_falha_fica_no_dataframe_com_motivo_falha(tmp_path, mocker):
    """O CNJ cuja busca falha não some do DataFrame (#460): sai numa linha com o motivo, ao lado do lido.

    Antes, ele saía só no log, e o DataFrame trazia um processo de dois
    pedidos como se fosse o resultado inteiro.
    """
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    sem_conexao = "1000000-00.2024.8.26.0001"
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=requests.ConnectionError("recusada"),
        match=[query_param_matcher({"dePesquisaNuUnificado": sem_conexao}, strict_match=False)],
    )

    aviso = rf"TJSPScraper\.cposg: 1 consulta\(s\) de processo falharam\. Falhas: {sem_conexao}: conexao"
    with pytest.warns(UserWarning, match=aviso):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg([CNJ, sem_conexao])

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": None},
        {"processo": sem_conexao, "motivo_falha": "conexao"},
    ]
    assert df.iloc[1].drop(["processo", "motivo_falha"]).isna().all()
    assert list(df.columns) == CPOSG_COLUNAS_ORDENADAS


def test_cposg_parse_arquivo_ilegivel_vira_linha_com_motivo_falha(tmp_path):
    """Arquivo baixado que o parser recusa fica no DataFrame com ``resposta_inesperada``, e não só no log."""
    pasta = tmp_path / "cposg" / "10001497120248260346"
    pasta.mkdir(parents=True)
    (pasta / "10001497120248260346_cd_processo_X.html").write_bytes(b"\xff\xfe\xfa invalido em utf-8")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=r"cposg_parse: 1 leitura\(s\) de arquivo falharam"):
        df = scraper.cposg_parse(str(tmp_path))

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": "resposta_inesperada"},
    ]


@responses.activate
def test_cposg_incidente_que_falha_nao_deixa_os_outros_como_processo_completo(tmp_path, mocker):
    """Com o modal de incidentes, a falha de um ``show.do`` não grava os anteriores: o CNJ sai só como falha.

    Antes, o primeiro incidente ficava na pasta e era lido como o processo,
    sem sinal de que faltavam os outros.
    """
    mocker.patch("time.sleep")
    cnj_modal = "1502870-48.2020.8.26.0161"
    responses.add(responses.GET, f"{ESAJ}/cposg/open.do", body=load_sample_bytes("tjsp", "cposg/open.html"))
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "acordao/modal_incidentes/search.html"),
        content_type="text/html;charset=UTF-8",
        match=[query_param_matcher({"dePesquisaNuUnificado": cnj_modal}, strict_match=False)],
    )
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/show.do",
        body=load_sample_bytes("tjsp", "cposg/show_com_incidentes.html"),
        content_type="text/html;charset=UTF-8",
        match=[query_param_matcher({"processo.codigo": "RI009HVDD0000"})],
    )
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/show.do",
        status=500,
        match=[query_param_matcher({"processo.codigo": "RI009HVDD12KW"})],
    )
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=f"{cnj_modal}: http_500"):
        falhas = scraper.cposg_download(cnj_modal)

    assert falhas == {cnj_modal: "http_500"}
    assert not list(tmp_path.rglob("*.html"))


@responses.activate
def test_cposg_pagina_que_nao_e_de_processo_sai_como_falha(tmp_path, mocker):
    """A busca que volta com o formulário (sem processo nem mensagem) não some do DataFrame em silêncio."""
    mocker.patch("time.sleep")
    _registrar_busca()
    responses.replace(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        content_type="text/html; charset=utf-8",
    )

    with pytest.warns(UserWarning, match="não é a página de um processo"):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ)

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": "resposta_inesperada"},
    ]


@responses.activate
def test_cposg_pausa_entre_processos_tambem_depois_de_um_erro(tmp_path, mocker):
    """O processo que falha não encurta o intervalo até a busca seguinte: o eSAJ bloqueia buscas em sequência."""
    pausas = mocker.patch("juscraper.courts.tjsp.cposg_download.time.sleep")
    sem_conexao = "1000000-00.2024.8.26.0001"
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/open.do",
        body=requests.ConnectionError("recusada"),
        match=[query_param_matcher({"gateway": "true"})],
    )

    with pytest.warns(UserWarning, match=f"{sem_conexao}: conexao"):
        jus.scraper("tjsp", download_path=str(tmp_path), sleep_time=0.7).cposg_download([sem_conexao, sem_conexao])

    assert [c.args for c in pausas.call_args_list] == [(0.7,), (0.7,)]


@responses.activate
def test_cposg_falhas_de_download_e_de_leitura_saem_num_unico_aviso(tmp_path, mocker):
    """Lote com falha de download e de leitura avisa uma vez, com as duas; antes, saíam dois avisos."""
    mocker.patch("time.sleep")
    _registrar_busca()
    # A busca do CNJ volta com o formulário: arquivo gravado que não é página de processo.
    responses.replace(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher({"dePesquisaNuUnificado": CNJ}, strict_match=False)],
    )
    sem_conexao = "1000000-00.2024.8.26.0001"
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=requests.ConnectionError("recusada"),
        match=[query_param_matcher({"dePesquisaNuUnificado": sem_conexao}, strict_match=False)],
    )

    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg([sem_conexao, CNJ])

    assert len(avisos) == 1
    mensagem = str(avisos[0].message)
    assert mensagem.startswith(
        "TJSPScraper.cposg: 2 consulta(s) de processo ou leitura(s) de arquivo falharam. "
        f"Falhas: {sem_conexao}: conexao; "
    )
    assert "resposta_inesperada (não é a página de um processo)" in mensagem
    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": "resposta_inesperada"},
        {"processo": sem_conexao, "motivo_falha": "conexao"},
    ]


@responses.activate
def test_cposg_le_so_os_processos_do_lote(tmp_path, mocker):
    """Processo e falha de um ``cposg_download`` anterior na mesma pasta ficam fora do composto."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    sem_conexao = "1000000-00.2024.8.26.0001"
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=requests.ConnectionError("recusada"),
        match=[query_param_matcher({"dePesquisaNuUnificado": sem_conexao}, strict_match=False)],
    )
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.warns(UserWarning, match=f"{sem_conexao}: conexao"):
        scraper.cposg_download(sem_conexao)
    anterior = tmp_path / "cposg" / "10093677620178260344"
    anterior.mkdir(parents=True)
    (anterior / "show.html").write_text(load_sample("tjsp", "cposg/show.html"), encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = scraper.cposg(CNJ)

    assert df[["processo", "motivo_falha"]].to_dict("records") == [{"processo": CNJ, "motivo_falha": None}]


@responses.activate
def test_cposg_parse_devolve_o_processo_que_o_download_nao_baixou(tmp_path, mocker):
    """No fluxo em duas etapas, o CNJ que o download não baixou sai no DataFrame, como no ``cposg``."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    sem_conexao = "1000000-00.2024.8.26.0001"
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=requests.ConnectionError("recusada"),
        match=[query_param_matcher({"dePesquisaNuUnificado": sem_conexao}, strict_match=False)],
    )
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=rf"cposg_download: .*{sem_conexao}: conexao.*cposg_parse os devolve"):
        scraper.cposg_download([CNJ, sem_conexao])
    with pytest.warns(UserWarning, match=rf"cposg_parse: 1 consulta\(s\) de processo falharam.*{sem_conexao}"):
        df = scraper.cposg_parse(str(tmp_path))

    assert df[["processo", "motivo_falha"]].to_dict("records") == [
        {"processo": CNJ, "motivo_falha": None},
        {"processo": sem_conexao, "motivo_falha": "conexao"},
    ]


@responses.activate
def test_cposg_processo_baixado_antes_nao_sai_tambem_como_falha(tmp_path, mocker):
    """O CNJ já baixado na pasta que falha num download seguinte sai uma vez, pelo arquivo, sem linha de falha."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    scraper.cposg_download(CNJ)
    responses.replace(
        responses.GET,
        f"{ESAJ}/cposg/search.do",
        body=requests.ConnectionError("recusada"),
    )
    with pytest.warns(UserWarning, match=f"{CNJ}: conexao"):
        scraper.cposg_download(CNJ)

    df = scraper.cposg_parse(str(tmp_path))

    assert df[["processo", "motivo_falha"]].to_dict("records") == [{"processo": CNJ, "motivo_falha": None}]
