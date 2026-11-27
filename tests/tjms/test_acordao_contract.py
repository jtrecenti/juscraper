"""Contratos offline de ``TJMSScraper.baixar_acordao`` e ``baixar_acordaos`` (#466).

O código é o de :mod:`juscraper.courts._esaj.acordao_cjsg`, que o TJCE também
usa; validação dos códigos, erros de rede e colunas exigidas estão em
``tests/tjce/test_acordao_contract.py``. Aqui fica o que é do TJMS: a URL do
tribunal e as linhas reais do cjsg dele (``samples/cjsg/single_page.html``).

``cjsg/getArquivo.do`` devolve o PDF direto no TJMS (sonda de 2026-10-31); o
corpo é :data:`PDF_FALSO`, porque o método só confere o prefixo ``%PDF``. A
resposta que não é PDF é a página real de reCAPTCHA que a mesma rota devolve
no TJAC (``tests/tjac/samples/acordao/getarquivo_recaptcha.html``).
"""

from pathlib import Path

import pandas as pd
import pytest
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.core.base import _texto_ausente_como_none
from juscraper.courts._esaj.parse import _parse_single_page
from juscraper.courts._esaj.pasta import DocumentoNaoPdfError
from tests._helpers import PDF_FALSO, load_sample_bytes, params_enviados

GET_ARQUIVO = "https://esaj.tjms.jus.br/cjsg/getArquivo.do"
CD_ACORDAO, CD_FORO = "122903", "0"
RECAPTCHA = ("tjac", "acordao/getarquivo_recaptcha.html")


def _cjsg():
    """A tabela como ``cjsg()`` a devolve: o embrulho público troca o ausente por ``None``."""
    return _texto_ausente_como_none(_parse_single_page(str(Path(__file__).parent / "samples/cjsg/single_page.html")))


def _registrar(cd_acordao=CD_ACORDAO, body=PDF_FALSO, content_type="application/pdf;charset=UTF-8"):
    responses.add(
        responses.GET,
        GET_ARQUIVO,
        body=body,
        content_type=content_type,
        match=[query_param_matcher({"cdAcordao": cd_acordao, "cdForo": CD_FORO})],
    )


@pytest.fixture
def tjms(tmp_path, mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjms", download_path=str(tmp_path))


def test_cjsg_traz_cd_acordao_e_cd_foro():
    linha = _cjsg().iloc[0]

    assert (linha.cd_acordao, linha.cd_foro) == (CD_ACORDAO, CD_FORO)


@responses.activate
def test_baixar_acordao_grava_o_pdf_de_get_arquivo(tjms, tmp_path):
    _registrar()
    linha = _cjsg().iloc[0]

    caminho = tjms.baixar_acordao(linha.cd_acordao, linha.cd_foro, diretorio=str(tmp_path / "destino"))

    assert caminho == str(tmp_path / "destino" / "acordaos" / f"{CD_ACORDAO}.pdf")
    assert Path(caminho).read_bytes() == PDF_FALSO
    (chamada,) = responses.calls
    assert params_enviados(chamada.request) == {"cdAcordao": CD_ACORDAO, "cdForo": CD_FORO}


@responses.activate
def test_baixar_acordao_recusa_pagina_de_captcha(tjms, tmp_path):
    _registrar(body=load_sample_bytes(*RECAPTCHA), content_type="text/html;charset=UTF-8")

    with pytest.raises(DocumentoNaoPdfError, match="nada foi gravado") as erro:
        tjms.baixar_acordao(CD_ACORDAO, CD_FORO)

    assert erro.value.motivo == "nao_pdf"
    assert not list(tmp_path.rglob("*.pdf"))


@responses.activate
def test_baixar_acordaos_por_linha_com_falhas_num_aviso(tjms, tmp_path):
    cjsg = _cjsg()
    _registrar()
    _registrar(cjsg.iloc[1].cd_acordao, body=load_sample_bytes(*RECAPTCHA), content_type="text/html;charset=UTF-8")

    with pytest.warns(UserWarning, match=f"{cjsg.iloc[1].processo}: nao_pdf"):
        resultado = tjms.baixar_acordaos(cjsg)

    assert list(resultado.columns) == [*cjsg.columns, "caminho_acordao", "motivo_falha"]
    assert resultado["caminho_acordao"].tolist() == [str(tmp_path / "acordaos" / f"{CD_ACORDAO}.pdf"), None]
    assert resultado["motivo_falha"].tolist() == [None, "nao_pdf"]
    pd.testing.assert_frame_equal(resultado[cjsg.columns], cjsg)
