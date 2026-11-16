"""Contratos offline do download de inteiro teor do STM.

Os dois endereços devolvem o PDF direto (sonda de 16/11/2026). O PDF em si
não é sample: aos contratos basta um corpo que comece com ``%PDF``.
"""
from pathlib import Path

import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.stm.inteiro_teor import InteiroTeorIndisponivelError
from tests._helpers import load_sample_bytes

PDF = b"%PDF-1.4\n%\xc7\xec\x8f\xa2\n1 0 obj\nendobj\n%%EOF\n"
UUID = "cbb3c68a2a6c472eef9576d05988cef88459cc90295cd7a818e1b04802c93d21"
# Os dois formatos da coluna ``url_inteiro_teor`` nos samples do cjsg.
URL_EPROC = f"https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=visualizar_acordao&uuid={UUID}"
URL_WWW2 = "https://www2.stm.jus.br/pesquisa/acordao/2015/50/10022722/10022722.pdf"


def _arquivos(pasta: Path) -> list[Path]:
    return [arquivo for arquivo in pasta.rglob("*") if arquivo.is_file()]


@pytest.mark.parametrize(
    ("url", "nome"),
    [
        (URL_EPROC, f"{UUID}.pdf"),
        (URL_WWW2, "2015_50_10022722.pdf"),
        # O mesmo nome de arquivo em anos e classes diferentes: são acórdãos distintos.
        ("https://www2.stm.jus.br/pesquisa/acordao/2007/40/01.0508376/01.0508376.pdf", "2007_40_01.0508376.pdf"),
        ("https://www2.stm.jus.br/pesquisa/acordao/2008/160/01.0508376/01.0508376.pdf", "2008_160_01.0508376.pdf"),
        # Sem a pasta do documento, como em alguns endereços do cjsg.
        ("https://www2.stm.jus.br/pesquisa/acordao/2006/160/01.0000012.34.pdf", "2006_160_01.0000012.34.pdf"),
    ],
)
@responses.activate
def test_pdf_e_gravado_como_veio(tmp_path, url, nome):
    responses.add(responses.GET, url, body=PDF, content_type="application/pdf")

    caminho = jus.scraper("stm").baixar_inteiro_teor(url, diretorio=str(tmp_path))

    assert responses.calls[0].request.url == url
    assert Path(caminho) == tmp_path / "inteiro_teor" / nome
    assert Path(caminho).read_bytes() == PDF


@responses.activate
def test_sem_diretorio_grava_no_download_path(tmp_path):
    responses.add(responses.GET, URL_WWW2, body=PDF, content_type="application/pdf")

    caminho = jus.scraper("stm", download_path=str(tmp_path)).baixar_inteiro_teor(URL_WWW2)

    assert Path(caminho) == tmp_path / "inteiro_teor" / "2015_50_10022722.pdf"


@pytest.mark.parametrize(
    "url",
    [
        None,
        float("nan"),
        "",
        "http://www2.stm.jus.br/pesquisa/acordao/2015/50/10022722/10022722.pdf",
        "https://www2.stm.jus.br/pesquisa/acordao/2015/50/10022722/",
        "https://www2.stm.jus.br/outra/pasta/10022722.pdf",
        "https://www2.stm.jus.br/pesquisa/acordao/2015/50/../10022722.pdf",
        "https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=outra&uuid=abc123",
        "https://eproc2g.stm.jus.br/outro.php?acao=visualizar_acordao&uuid=abc123",
        "https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=visualizar_acordao",
        "https://eproc2g.stm.jus.br/eproc_2g_prod/externo_controlador.php?acao=visualizar_acordao&uuid=../x",
        "https://exemplo.com/pesquisa/acordao/2015/50/10022722/10022722.pdf",
    ],
)
@responses.activate
def test_endereco_fora_do_formato_levanta_antes_do_pedido(tmp_path, url):
    with pytest.raises(ValueError, match="url_inteiro_teor"):
        jus.scraper("stm").baixar_inteiro_teor(url, diretorio=str(tmp_path))

    assert len(responses.calls) == 0


@responses.activate
def test_resposta_sem_pdf_levanta_e_nao_grava(tmp_path):
    responses.add(responses.GET, URL_EPROC, body="<html>Acórdão não encontrado</html>", content_type="text/html")

    with pytest.raises(InteiroTeorIndisponivelError, match="sem PDF") as erro:
        jus.scraper("stm").baixar_inteiro_teor(URL_EPROC, diretorio=str(tmp_path))

    assert erro.value.url == URL_EPROC
    assert _arquivos(tmp_path) == []


@responses.activate
def test_erro_http_levanta_o_erro_do_inteiro_teor(tmp_path):
    responses.add(responses.GET, URL_WWW2, status=404)

    with pytest.raises(InteiroTeorIndisponivelError, match="404"):
        jus.scraper("stm").baixar_inteiro_teor(URL_WWW2, diretorio=str(tmp_path))

    assert _arquivos(tmp_path) == []


@responses.activate
def test_bloqueio_do_waf_levanta_e_nao_grava(tmp_path):
    """Em 16/11/2026, ``www2`` devolveu a um IP de datacenter a mesma página do WAF do portal."""
    responses.add(
        responses.GET,
        URL_WWW2,
        body=load_sample_bytes("stm", "cjsg/waf_rejected.html"),
        content_type="text/html; charset=utf-8",
    )

    with pytest.raises(BotChallengeBlockedError, match="Request Rejected"):
        jus.scraper("stm").baixar_inteiro_teor(URL_WWW2, diretorio=str(tmp_path))

    assert _arquivos(tmp_path) == []
