"""Offline contract tests for TJSP cposg (``method='html'``).

HTML flow: GET ``cposg/open.do`` → GET ``cposg/search.do`` → Caso 3
(resposta simples) or Caso 1/2 (listagem/modal). The CNJ used here lands
in Caso 3 — the search response itself contains the process details and
the scraper saves it under the ``cdProcesso`` value. The page leaves the
movements to ``carregarMovimentacoesAjax.do`` (five rows per page, next page
by ``cursor``), which the scraper follows and writes into the saved HTML.
"""
import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.courts._esaj.acordao import parse_cursor
from tests._helpers import load_sample, load_sample_bytes

ESAJ = "https://esaj.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"

CPOSG_BASICOS_MIN = {"id_original", "classe", "status"}

# Ordem pública das colunas do cposg HTML. A lista é literal de propósito: se o
# teste importasse a constante do módulo testado, uma reordenação dela passaria.
CPOSG_COLUNAS_ORDENADAS = [
    "id_original", "processo", "status", "classe", "assunto", "secao",
    "orgao_julgador", "area", "relator", "valor_da_acao", "origem",
    "volume_apenso", "movimentacoes", "partes", "historico", "decisoes",
    "composicao", "primeira_inst",
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
    """Sem a sessão do processo, o eSAJ devolve uma página inteira, sem a tabela: nada é gravado."""
    mocker.patch("time.sleep")
    _registrar_busca()
    responses.add(
        responses.GET,
        f"{ESAJ}/cposg/carregarMovimentacoesAjax.do",
        body=load_sample_bytes("tjsp", "cposg/open.html"),
        status=200,
        content_type="text/html;charset=UTF-8",
    )

    with pytest.raises(RuntimeError, match="Nenhum processo foi baixado"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

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

    with pytest.raises(RuntimeError, match="Nenhum processo foi baixado"):
        jus.scraper("tjsp", download_path=str(tmp_path)).cposg(CNJ, method="html")

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
def test_cposg_processo_sem_informacoes_sai_em_aviso(tmp_path, mocker):
    """O número que o 2º grau não tem fica fora do DataFrame, mas o aviso o nomeia."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_movimentacoes()
    _registrar_busca_sem_informacoes()

    with pytest.warns(UserWarning, match=f"não mostra 1 processo.*{CNJ_SEM_INFORMACOES}"):
        df = jus.scraper("tjsp", download_path=str(tmp_path)).cposg([CNJ_SEM_INFORMACOES, CNJ])

    assert df["processo"].tolist() == [CNJ]


@responses.activate
def test_cposg_so_processo_sem_informacoes_avisa_e_falha(tmp_path, mocker):
    """Sem nenhum processo baixado, o erro de sempre vem depois do aviso que diz por quê."""
    mocker.patch("time.sleep")
    _registrar_busca()
    _registrar_busca_sem_informacoes()
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=CNJ_SEM_INFORMACOES), \
            pytest.raises(RuntimeError, match="Nenhum processo foi baixado"):
        scraper.cposg_download(CNJ_SEM_INFORMACOES)

    assert not (tmp_path / "cposg").exists()
