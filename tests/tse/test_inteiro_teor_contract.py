"""Contratos offline do download de inteiro teor do TSE."""
from pathlib import Path

import pytest
import responses

import juscraper as jus
from juscraper.courts.tse.download import INTEIRO_TEOR_URL, InteiroTeorIndisponivelError, LimiteDeRequisicoesError
from tests._helpers import load_sample_bytes

PDF_PURO = load_sample_bytes("tse", "inteiro_teor/pdf_puro.bin")
ENVELOPE = load_sample_bytes("tse", "inteiro_teor/envelope_multipart.bin")
TEXTO = "text/plain;charset=UTF-8"


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
@pytest.mark.parametrize("codigo", ["", "abc", "12a", "1/2", "../1", -1, 1.5, None, True, "１２"])
def test_codigo_invalido_e_recusado_antes_do_pedido(codigo, tmp_path):
    with pytest.raises(ValueError, match="codigo_decisao"):
        jus.scraper("tse").baixar_inteiro_teor(codigo, diretorio=str(tmp_path))

    assert len(responses.calls) == 0


@responses.activate
def test_pedidos_seguidos_guardam_sleep_time(mocker, tmp_path):
    _registrar("2972172", PDF_PURO)
    _registrar("3522031", ENVELOPE)
    relogio = mocker.patch("juscraper.courts.tse.client.time.monotonic", side_effect=[100.0, 103.0, 110.0])
    espera = mocker.patch("juscraper.courts.tse.client.time.sleep")
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
    mocker.patch("juscraper.courts.tse.client.time.monotonic", side_effect=[50.0, 51.0, 60.0])
    espera = mocker.patch("juscraper.courts.tse.client.time.sleep")
    tse = jus.scraper("tse", sleep_time=4)

    with pytest.raises(InteiroTeorIndisponivelError):
        tse.baixar_inteiro_teor(1, diretorio=str(tmp_path))
    tse.baixar_inteiro_teor(2972172, diretorio=str(tmp_path))

    espera.assert_called_once_with(3.0)


def test_cjsg_e_stub_que_explica_o_captcha():
    with pytest.raises(NotImplementedError, match="captcha"):
        jus.scraper("tse").cjsg("propaganda eleitoral")
