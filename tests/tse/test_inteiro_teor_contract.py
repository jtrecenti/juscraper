"""Contratos offline do download de inteiro teor do TSE."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.core.intervalo import IntervaloEntrePedidos
from juscraper.courts.tse.client import TSEScraper
from juscraper.courts.tse.download import INTEIRO_TEOR_URL, InteiroTeorIndisponivelError, LimiteDeRequisicoesError
from tests._helpers import load_sample_bytes

PDF_PURO = load_sample_bytes("tse", "inteiro_teor/pdf_puro.bin")
ENVELOPE = load_sample_bytes("tse", "inteiro_teor/envelope_multipart.bin")
TEXTO = "text/plain;charset=UTF-8"


@pytest.fixture(autouse=True)
def _intervalo_novo(monkeypatch):
    """O intervalo de inteiro teor é da classe: sem isto, um teste esperaria pelo pedido do anterior."""
    monkeypatch.setattr(TSEScraper, "_intervalo_inteiro_teor", IntervaloEntrePedidos())


def _registrar(codigo: str, corpo: bytes, content_type: str = "application/pdf") -> None:
    responses.add(responses.GET, f"{INTEIRO_TEOR_URL}/{codigo}", body=corpo, content_type=content_type)


def _pdfs(pasta: Path) -> list[Path]:
    return [arquivo for arquivo in pasta.rglob("*") if arquivo.is_file()]


@responses.activate
def test_pdf_puro_e_gravado_como_veio(tmp_path):
    _registrar("2972172", PDF_PURO)

    caminho = jus.scraper("tse").baixar_inteiro_teor(2972172, diretorio=str(tmp_path))

    assert Path(caminho) == tmp_path / "inteiro_teor" / "2972172.pdf"
    assert Path(caminho).read_bytes() == PDF_PURO


@responses.activate
def test_envelope_multipart_e_desembrulhado(tmp_path):
    # O serviço manda ``Content-Type: application/pdf`` com o PDF dentro de um multipart.
    assert ENVELOPE.startswith(b"--")
    _registrar("3522031", ENVELOPE)

    caminho = jus.scraper("tse").baixar_inteiro_teor("3522031", diretorio=str(tmp_path))

    gravado = Path(caminho).read_bytes()
    assert gravado.startswith(b"%PDF-")
    assert gravado.rstrip().endswith(b"%%EOF")
    assert gravado in ENVELOPE
    assert b"Content-Disposition" not in gravado


@responses.activate
@pytest.mark.parametrize("codigo", [np.int64(2972172), 2972172.0, np.float64(2972172)])
def test_codigo_inteiro_do_numpy_e_float_inteiro_sao_aceitos(codigo, tmp_path):
    _registrar("2972172", PDF_PURO)

    caminho = jus.scraper("tse").baixar_inteiro_teor(codigo, diretorio=str(tmp_path))

    assert Path(caminho).name == "2972172.pdf"


@responses.activate
def test_status_retentavel_ganha_uma_nova_tentativa_depois_do_intervalo(mocker, tmp_path):
    espera = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, f"{INTEIRO_TEOR_URL}/2972172", status=503)
    _registrar("2972172", PDF_PURO)

    jus.scraper("tse").baixar_inteiro_teor(2972172, diretorio=str(tmp_path))

    espera.assert_called_once_with(10.0)


@responses.activate
def test_sem_diretorio_grava_em_download_path(tmp_path):
    _registrar("2972172", PDF_PURO)
    tse = jus.scraper("tse", download_path=str(tmp_path))

    caminho = tse.baixar_inteiro_teor(2972172)

    assert Path(caminho) == tmp_path / "inteiro_teor" / "2972172.pdf"


@responses.activate
def test_codigo_inexistente_levanta_erro_e_nao_grava(tmp_path):
    _registrar("1", load_sample_bytes("tse", "inteiro_teor/codigo_inexistente.txt"), TEXTO)

    with pytest.raises(InteiroTeorIndisponivelError, match="SitDoc") as erro:
        jus.scraper("tse").baixar_inteiro_teor(1, diretorio=str(tmp_path))

    assert not isinstance(erro.value, LimiteDeRequisicoesError)
    assert erro.value.codigo_decisao == "1"
    assert _pdfs(tmp_path) == []


@responses.activate
def test_excesso_de_requisicoes_levanta_erro_proprio(tmp_path):
    # HTTP 200 com a recusa em texto: não é status retentável, e o pedido não se repete.
    _registrar("3522031", load_sample_bytes("tse", "inteiro_teor/excesso_requisicoes.txt"), TEXTO)

    with pytest.raises(LimiteDeRequisicoesError, match="Excesso de requisições"):
        jus.scraper("tse").baixar_inteiro_teor(3522031, diretorio=str(tmp_path))

    assert len(responses.calls) == 1
    assert _pdfs(tmp_path) == []


@responses.activate
def test_envelope_cortado_nao_e_gravado(tmp_path):
    _registrar("3522031", ENVELOPE[: len(ENVELOPE) // 2])

    with pytest.raises(InteiroTeorIndisponivelError, match="sem PDF"):
        jus.scraper("tse").baixar_inteiro_teor(3522031, diretorio=str(tmp_path))

    assert _pdfs(tmp_path) == []


@responses.activate
@pytest.mark.parametrize(
    "codigo", ["", "abc", "12a", "1/2", "../1", -1, 1.5, float("nan"), float("inf"), None, True, "１２"]
)
def test_codigo_invalido_e_recusado_antes_do_pedido(codigo, tmp_path):
    with pytest.raises(ValueError, match="codigo_decisao"):
        jus.scraper("tse").baixar_inteiro_teor(codigo, diretorio=str(tmp_path))

    assert len(responses.calls) == 0


@responses.activate
def test_pedidos_seguidos_guardam_sleep_time(mocker, tmp_path):
    _registrar("2972172", PDF_PURO)
    _registrar("3522031", ENVELOPE)
    relogio = mocker.patch("juscraper.core.intervalo.time.monotonic", side_effect=[100.0, 103.0, 110.0])
    espera = mocker.patch("juscraper.core.intervalo.time.sleep")
    tse = jus.scraper("tse")

    tse.baixar_inteiro_teor(2972172, diretorio=str(tmp_path))
    espera.assert_not_called()
    tse.baixar_inteiro_teor(3522031, diretorio=str(tmp_path))

    # O primeiro pedido terminou em 100; em 103 faltam 7 dos 10 s do default.
    espera.assert_called_once_with(7.0)
    assert relogio.call_count == 3


@responses.activate
def test_pedido_que_falha_tambem_conta_para_o_intervalo(mocker, tmp_path):
    _registrar("1", load_sample_bytes("tse", "inteiro_teor/codigo_inexistente.txt"), TEXTO)
    _registrar("2972172", PDF_PURO)
    mocker.patch("juscraper.core.intervalo.time.monotonic", side_effect=[50.0, 51.0, 60.0])
    espera = mocker.patch("juscraper.core.intervalo.time.sleep")
    tse = jus.scraper("tse", sleep_time=4)

    with pytest.raises(InteiroTeorIndisponivelError):
        tse.baixar_inteiro_teor(1, diretorio=str(tmp_path))
    tse.baixar_inteiro_teor(2972172, diretorio=str(tmp_path))

    espera.assert_called_once_with(3.0)


@responses.activate
def test_instancias_diferentes_dividem_o_intervalo(mocker, tmp_path):
    # O serviço não distingue as instâncias: a segunda espera pelo pedido da primeira.
    _registrar("2972172", PDF_PURO)
    _registrar("3522031", ENVELOPE)
    mocker.patch("juscraper.core.intervalo.time.monotonic", side_effect=[100.0, 103.0, 110.0])
    espera = mocker.patch("juscraper.core.intervalo.time.sleep")

    jus.scraper("tse").baixar_inteiro_teor(2972172, diretorio=str(tmp_path))
    jus.scraper("tse", sleep_time=5).baixar_inteiro_teor(3522031, diretorio=str(tmp_path))

    # Vale o ``sleep_time`` da instância que faz o pedido: faltam 2 dos 5 s.
    espera.assert_called_once_with(2.0)


@pytest.fixture
def sem_espera(mocker):
    return mocker.patch("juscraper.core.intervalo.time.sleep")


@responses.activate
@pytest.mark.usefixtures("sem_espera")
def test_lote_devolve_uma_linha_por_codigo_com_o_motivo_da_falha(tmp_path):
    _registrar("2972172", PDF_PURO)
    _registrar("1", load_sample_bytes("tse", "inteiro_teor/codigo_inexistente.txt"), TEXTO)
    _registrar("3522031", load_sample_bytes("tse", "inteiro_teor/excesso_requisicoes.txt"), TEXTO)
    responses.add(responses.GET, f"{INTEIRO_TEOR_URL}/7", status=404)
    _registrar("8", ENVELOPE)

    with pytest.warns(UserWarning, match=r"3 download\(s\) de inteiro teor falharam.*1: nao_pdf") as avisos:
        df = jus.scraper("tse").baixar_inteiros_teores([2972172, "1", np.int64(3522031), 7, 8], diretorio=str(tmp_path))

    assert len(avisos) == 1
    assert list(df.columns) == ["codigo_decisao", "caminho_inteiro_teor", "motivo_falha"]
    assert df["codigo_decisao"].tolist() == [2972172, "1", 3522031, 7, 8]
    assert df["motivo_falha"].tolist() == [None, "nao_pdf", "limite_de_requisicoes", "http_404", None]
    assert df["caminho_inteiro_teor"].tolist() == [
        str(tmp_path / "inteiro_teor" / "2972172.pdf"), None, None, None, str(tmp_path / "inteiro_teor" / "8.pdf"),
    ]
    assert sorted(arquivo.name for arquivo in _pdfs(tmp_path)) == ["2972172.pdf", "8.pdf"]


@responses.activate
def test_lote_guarda_sleep_time_entre_os_pedidos(mocker, tmp_path):
    _registrar("2972172", PDF_PURO)
    _registrar("3522031", ENVELOPE)
    mocker.patch("juscraper.core.intervalo.time.monotonic", side_effect=[100.0, 100.5, 111.0])
    espera = mocker.patch("juscraper.core.intervalo.time.sleep")

    df = jus.scraper("tse").baixar_inteiros_teores(["2972172", "3522031"], diretorio=str(tmp_path))

    espera.assert_called_once_with(9.5)
    assert df["motivo_falha"].isna().all()


@responses.activate
def test_lote_sem_falha_nao_avisa(tmp_path, recwarn):
    _registrar("2972172", PDF_PURO)

    df = jus.scraper("tse", download_path=str(tmp_path)).baixar_inteiros_teores(pd.Series([2972172]))

    assert df["caminho_inteiro_teor"].tolist() == [str(tmp_path / "inteiro_teor" / "2972172.pdf")]
    assert [aviso for aviso in recwarn if issubclass(aviso.category, UserWarning)] == []


@responses.activate
def test_lote_vazio_devolve_as_colunas_sem_pedido():
    df = jus.scraper("tse").baixar_inteiros_teores([])

    assert list(df.columns) == ["codigo_decisao", "caminho_inteiro_teor", "motivo_falha"]
    assert df.empty
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.usefixtures("sem_espera")
def test_lote_poe_codigo_invalido_em_linha_sem_pedido(tmp_path):
    # A coluna de códigos com célula vazia volta do CSV como float, com NaN na vazia.
    _registrar("2972172", PDF_PURO)
    _registrar("3522031", ENVELOPE)

    with pytest.warns(UserWarning, match="2 download"):
        df = jus.scraper("tse").baixar_inteiros_teores(
            pd.Series([2972172.0, float("nan"), "abc", 3522031.0]), diretorio=str(tmp_path)
        )

    assert df["motivo_falha"].tolist() == [None, "entrada_invalida", "entrada_invalida", None]
    assert sorted(arquivo.name for arquivo in _pdfs(tmp_path)) == ["2972172.pdf", "3522031.pdf"]
    assert len(responses.calls) == 2


@responses.activate
@pytest.mark.usefixtures("sem_espera")
def test_lote_para_em_duas_recusas_seguidas(tmp_path):
    recusa = load_sample_bytes("tse", "inteiro_teor/excesso_requisicoes.txt")
    _registrar("1", recusa, TEXTO)
    _registrar("2972172", PDF_PURO)
    _registrar("3", recusa, TEXTO)
    _registrar("4", recusa, TEXTO)

    with pytest.warns(UserWarning, match="4 download"):
        df = jus.scraper("tse").baixar_inteiros_teores([1, 2972172, 3, 4, 5], diretorio=str(tmp_path))

    # Uma recusa isolada não para o lote; duas seguidas, sim, e o código 5 não é pedido.
    assert df["motivo_falha"].tolist() == [
        "limite_de_requisicoes", None, "limite_de_requisicoes", "limite_de_requisicoes", "limite_de_requisicoes",
    ]
    assert len(responses.calls) == 4


@responses.activate
@pytest.mark.parametrize("codigo", ["2972172", 2972172, np.int64(2972172), 2972172.0])
def test_lote_recusa_um_codigo_solto(codigo):
    # Um texto seria percorrido caractere a caractere, um pedido por dígito.
    with pytest.raises(TypeError, match="baixar_inteiro_teor"):
        jus.scraper("tse").baixar_inteiros_teores(codigo)

    assert len(responses.calls) == 0


def test_cjsg_e_stub_que_explica_o_captcha():
    with pytest.raises(NotImplementedError, match="captcha"):
        jus.scraper("tse").cjsg("propaganda eleitoral")
