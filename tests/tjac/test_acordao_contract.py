"""Contratos de ``baixar_acordao`` no TJAC, pela movimentação do processo.

Samples de ``tests/fixtures/capture/tjac.py``: o processo
0700021-98.2018.8.01.0001 tem dois acórdãos, a apelação (julgada em
13/04/2026, movimentação de 21/04, documento 8, tipo "Acórdão") e os
embargos (julgados em 27/10/2026, movimentação de 28/10, documento 33, tipo
"Embargos de Declaração"). As certidões entre os dois pedem senha.
"""

from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import requests
import responses

import juscraper as jus
from juscraper.courts._esaj.acordao import (
    AcordaoNaoEncontradoError,
    ProcessoNaoEncontradoError,
    RespostaInesperadaError,
    RespostaNaoPdfError,
    parse_parametros_pasta,
    tipo_documento,
)
from tests._helpers import PDF_FALSO, load_sample, registrar_rota_acordao

BASE = "https://esaj.tjac.jus.br/"
CNJ = "0700021-98.2018.8.01.0001"
CD_PROCESSO = "P0000213J0000"


@pytest.fixture
def tjac(tmp_path, mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjac", download_path=str(tmp_path))


def _chamadas(rota):
    return [c for c in responses.calls if urlparse(c.request.url).path.endswith(rota)]


@responses.activate
def test_baixa_acordao_da_apelacao_pela_data_de_julgamento(tjac, tmp_path):
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")

    caminho = tjac.baixar_acordao(CNJ, "13/04/2026")

    assert caminho == str(tmp_path / "acordaos" / f"07000219820188010001_{CD_PROCESSO}_8.pdf")
    assert Path(caminho).read_bytes() == PDF_FALSO
    busca = parse_qs(urlparse(_chamadas("search.do")[0].request.url).query, keep_blank_values=True)
    assert busca["dePesquisaNuUnificado"] == [CNJ]
    assert busca["numeroDigitoAnoUnificado"] == ["0700021-98.2018"]
    assert busca["foroNumeroUnificado"] == ["0001"]
    assert busca["uuidCaptcha"] == [""]
    parametros = parse_parametros_pasta(load_sample("tjac", f"acordao/dois_acordaos/pasta_{CD_PROCESSO}_8.html"))
    assert _chamadas("getPDF.do")[0].request.url == f"{BASE}pastadigital/getPDF.do?{parametros}"
    # As movimentações vêm na página do processo: sem AJAX nem show.do.
    assert not _chamadas("carregarMovimentacoesAjax.do")
    assert not _chamadas("show.do")


@responses.activate
def test_pula_documentos_com_senha_e_aceita_acordao_de_embargos(tjac):
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")

    caminho = tjac.baixar_acordao(CNJ, "22/04/2026")

    assert caminho.endswith(f"_{CD_PROCESSO}_33.pdf")
    verificados = [
        parse_qs(urlparse(c.request.url).query)["cdDocumento"][0] for c in _chamadas("verificarAcessoMovimentacao.do")
    ]
    # Do mais antigo ao mais novo a partir da data; cada 403 de senha uma vez só, sem retry.
    assert verificados == ["10", "11", "12", "13", "14", "16", "17", "19", "20", "21", "22", "23", "27", "33"]


@responses.activate
def test_sem_acordao_depois_da_data_explica_documentos_com_senha(tjac, tmp_path):
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")
    responses.add(
        responses.GET,
        f"{BASE}cposg5/verificarAcessoMovimentacao.do",
        body=load_sample("tjac", f"acordao/dois_acordaos/verificar_acesso_{CD_PROCESSO}_10.html"),
        status=403,
    )

    with pytest.raises(AcordaoNaoEncontradoError, match=r"29/10/2026.*1 pede\(m\) a senha do processo"):
        tjac.baixar_acordao(CNJ, "29/10/2026")

    assert not (tmp_path / "acordaos").exists()


@responses.activate
def test_processo_fora_da_consulta_publica(tjac):
    registrar_rota_acordao("tjac", "sem_informacoes", BASE, "cposg5/")

    with pytest.raises(ProcessoNaoEncontradoError, match="segredo de justiça") as erro:
        tjac.baixar_acordao("0700000-00.2026.8.01.0001", "01/01/2026")

    assert erro.value.motivo == "nao_encontrado"


@responses.activate
def test_resposta_que_nao_e_pdf_nao_vira_arquivo(tjac, tmp_path):
    responses.add(
        responses.GET,
        f"{BASE}pastadigital/getPDF.do",
        body="<html>Sessão expirada</html>",
        content_type="text/html;charset=UTF-8",
    )
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")

    with pytest.raises(RespostaNaoPdfError, match="Sessão expirada"):
        tjac.baixar_acordao(CNJ, "13/04/2026")

    assert not list(tmp_path.rglob("*.pdf"))


@responses.activate
def test_baixar_acordaos_devolve_caminho_e_motivo_por_linha(tjac):
    responses.add(
        responses.GET,
        f"{BASE}cposg5/search.do",
        body=load_sample("tjac", "acordao/sem_informacoes/search.html"),
        content_type="text/html;charset=UTF-8",
        match=[
            responses.matchers.query_param_matcher(
                {"dePesquisaNuUnificado": "0700000-00.2026.8.01.0001"}, strict_match=False
            )
        ],
    )
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")
    cjsg = pd.DataFrame(
        {
            "processo": [CNJ, "0700000-00.2026.8.01.0001", CNJ],
            "data_julgamento": ["13/04/2026", "01/01/2026", "27/10/2026"],
            "cd_acordao": ["1", "2", "3"],
        }
    )

    with pytest.warns(
        UserWarning, match=r"1 download\(s\) de acórdão falharam.*0700000-00.2026.8.01.0001: nao_encontrado"
    ):
        saida = tjac.baixar_acordaos(cjsg)

    assert list(saida.columns) == ["processo", "data_julgamento", "cd_acordao", "caminho_acordao", "motivo_falha"]
    assert saida["caminho_acordao"].str.rsplit("_", n=1).str[-1].tolist()[::2] == ["8.pdf", "33.pdf"]
    assert saida["caminho_acordao"].isna().tolist() == [False, True, False]
    assert saida["motivo_falha"].tolist() == [None, "nao_encontrado", None]


def test_baixar_acordaos_exige_colunas_do_cjsg(tjac):
    with pytest.raises(ValueError, match="data_julgamento"):
        tjac.baixar_acordaos(pd.DataFrame({"processo": [CNJ]}))


@pytest.mark.parametrize("data", ["2026-13-01", "ontem", 20260413])
def test_data_de_julgamento_invalida(tjac, data):
    with pytest.raises((ValueError, TypeError), match="data_julgamento"):
        tjac.baixar_acordao(CNJ, data)


@pytest.mark.parametrize("data", [date(2026, 4, 13), datetime(2026, 4, 13, 10, 30, tzinfo=timezone.utc), "2026-04-13"])
@responses.activate
def test_data_de_julgamento_aceita_date_e_formatos_canonicos(tjac, data):
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")

    assert tjac.baixar_acordao(CNJ, data).endswith(f"_{CD_PROCESSO}_8.pdf")


@pytest.mark.parametrize(
    ("rota", "corpo", "mensagem"),
    [
        ("cposg5/search.do", "<html><body></body></html>", "não devolveu processo"),
        ("pastadigital/abrirDocumentoEdt.do", "<html><body>pasta</body></html>", "não traz 'parametros'"),
    ],
)
@responses.activate
def test_pagina_fora_do_formato_levanta_resposta_inesperada(tjac, rota, corpo, mensagem):
    responses.add(responses.GET, f"{BASE}{rota}", body=corpo, content_type="text/html;charset=UTF-8")
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")

    with pytest.raises(RespostaInesperadaError, match=mensagem):
        tjac.baixar_acordao(CNJ, "13/04/2026")


@responses.activate
def test_baixar_acordaos_registra_falha_de_rede_e_segue(tjac):
    responses.add(responses.GET, f"{BASE}cposg5/search.do", body=requests.ConnectionError("sem rede"))
    responses.add(
        responses.GET, f"{BASE}cposg5/search.do",
        body=load_sample("tjac", "acordao/dois_acordaos/search.html"), content_type="text/html;charset=UTF-8",
    )
    registrar_rota_acordao("tjac", "dois_acordaos", BASE, "cposg5/")
    cjsg = pd.DataFrame({"processo": [CNJ, CNJ], "data_julgamento": ["13/04/2026", "13/04/2026"]})

    with pytest.warns(UserWarning, match=f"{CNJ}: conexao"):
        saida = tjac.baixar_acordaos(cjsg)

    assert saida["motivo_falha"].tolist() == ["conexao", None]


def test_parametros_sem_tipo_de_documento():
    assert tipo_documento("cdDocumento=1&numInicial=2") == ""
    assert tipo_documento("deTipoDocDigital=Ac%F3rd%E3o&cdForo=900") == "Acórdão"
