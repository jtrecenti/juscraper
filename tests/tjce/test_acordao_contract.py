"""Contratos offline de ``TJCEScraper.baixar_acordao`` e ``baixar_acordaos``.

As linhas vêm do parser do cjsg sobre a captura real
``samples/cjsg/results_normal_page_01.html``. ``cjsg/getArquivo.do`` devolve o
PDF direto (corpo sintético, porque nada lê o PDF) ou, para código que não
existe, a página real ``samples/acordao/arquivo_nao_localizado.html``.
"""

from functools import cache
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import pandas as pd
import pytest
import requests
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from juscraper.core.base import _texto_ausente_como_none
from juscraper.core.exceptions import BloqueioAntiBotWarning, BotChallengeBlockedError
from juscraper.courts._esaj.acordao import EntradaInvalidaError
from juscraper.courts._esaj.pasta import DocumentoNaoPdfError
from tests._helpers import PDF_FALSO, load_sample_bytes

URL = "https://esaj.tjce.jus.br/cjsg/getArquivo.do"
SAMPLES = Path(__file__).parent / "samples"


@cache
def _cjsg():
    """A tabela como ``cjsg()`` a devolve: o embrulho público troca o ausente por ``None``.

    Parseada uma vez; os testes que alteram a tabela trabalham numa cópia.
    """
    return _texto_ausente_como_none(
        jus.scraper("tjce").cjsg_parse(str(SAMPLES / "cjsg" / "results_normal_page_01.html"))
    )


def _registrar(cd_acordao, body=PDF_FALSO, content_type="application/pdf;charset=UTF-8"):
    responses.add(
        responses.GET,
        URL,
        body=body,
        content_type=content_type,
        match=[query_param_matcher({"cdAcordao": cd_acordao, "cdForo": "0"})],
    )


def _nao_localizado(cd_acordao):
    _registrar(cd_acordao, load_sample_bytes("tjce", "acordao/arquivo_nao_localizado.html"), "text/html;charset=UTF-8")


@pytest.fixture
def tjce(tmp_path, mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjce", download_path=str(tmp_path))


@responses.activate
def test_baixar_acordao_pede_get_arquivo_com_os_codigos_do_cjsg(tjce, tmp_path):
    linha = _cjsg().iloc[0]
    _registrar(linha.cd_acordao)

    caminho = tjce.baixar_acordao(linha.cd_acordao, linha.cd_foro, diretorio=str(tmp_path / "destino"))

    assert caminho == str(tmp_path / "destino" / "acordaos" / f"{linha.cd_acordao}.pdf")
    assert Path(caminho).read_bytes() == PDF_FALSO
    (chamada,) = responses.calls
    assert dict(parse_qsl(urlsplit(chamada.request.url).query)) == {"cdAcordao": "3834193", "cdForo": "0"}


@responses.activate
def test_baixar_acordao_usa_download_path_e_aceita_numero(tjce, tmp_path):
    _registrar("3846624")

    caminho = tjce.baixar_acordao(3846624, 0.0)

    assert caminho == str(tmp_path / "acordaos" / "3846624.pdf")


@responses.activate
def test_baixar_acordao_recusa_pagina_de_arquivo_nao_localizado(tjce, tmp_path):
    _nao_localizado("999999999")

    with pytest.raises(DocumentoNaoPdfError, match="Arquivo não localizado"):
        tjce.baixar_acordao("999999999", "0")

    assert not list(tmp_path.rglob("*.pdf"))


@pytest.mark.parametrize(
    ("campo", "valores"),
    [
        ("cd_acordao", ("../x", "0")),
        ("cd_acordao", ("", "0")),
        ("cd_acordao", (float("nan"), "0")),
        ("cd_foro", ("3846624", None)),
        ("cd_foro", ("3846624", "0&cdAcordao=1")),
        ("cd_acordao", ("３８４６６２４", "0")),
        ("cd_acordao", (3846624.5, "0")),
    ],
)
@responses.activate
def test_baixar_acordao_recusa_codigo_fora_do_formato_sem_pedido(tjce, campo, valores):
    with pytest.raises(EntradaInvalidaError, match=f"{campo} inválido"):
        tjce.baixar_acordao(*valores)

    assert len(responses.calls) == 0


@responses.activate
def test_baixar_acordaos_por_linha_com_falhas_num_aviso(tjce, tmp_path):
    cjsg = _cjsg().head(4).copy()
    _registrar(cjsg.iloc[0].cd_acordao)
    _nao_localizado(cjsg.iloc[1].cd_acordao)
    cjsg.loc[cjsg.index[2], "cd_acordao"] = None
    responses.add(
        responses.GET,
        URL,
        status=404,
        match=[query_param_matcher({"cdAcordao": cjsg.iloc[3].cd_acordao}, strict_match=False)],
    )

    with pytest.warns(UserWarning, match="download\\(s\\) de acórdão") as avisos:
        resultado = tjce.baixar_acordaos(cjsg)

    assert list(resultado.columns) == [*cjsg.columns, "caminho_acordao", "motivo_falha"]
    assert resultado["caminho_acordao"].tolist() == [
        str(tmp_path / "acordaos" / f"{cjsg.iloc[0].cd_acordao}.pdf"),
        None,
        None,
        None,
    ]
    assert resultado["motivo_falha"].tolist() == [None, "nao_pdf", "entrada_invalida", "http_404"]
    assert f"{cjsg.iloc[1].processo}: nao_pdf" in str(avisos[0].message)
    pd.testing.assert_frame_equal(resultado[cjsg.columns], cjsg)


@responses.activate
def test_baixar_acordaos_desafio_anti_bot_vira_motivo_da_linha(tjce):
    cjsg = _cjsg().head(1)
    responses.add(responses.GET, URL, body=BotChallengeBlockedError("TJCE", URL))

    with pytest.warns(UserWarning, match="bloqueio_anti_bot"):
        resultado = tjce.baixar_acordaos(cjsg)

    assert resultado["motivo_falha"].tolist() == ["bloqueio_anti_bot"]


@responses.activate
def test_baixar_acordaos_desafio_anti_bot_encerra_o_lote_sem_perder_as_linhas(tjce):
    """Bloqueio na linha 2 de 3: a linha 1 fica (#471), e a 3 sai ``bloqueio_anti_bot`` sem pedido."""
    cjsg = _cjsg().head(3)
    _registrar(cjsg.iloc[0].cd_acordao)
    responses.add(
        responses.GET,
        URL,
        body=BotChallengeBlockedError("TJCE", URL),
        match=[query_param_matcher({"cdAcordao": cjsg.iloc[1].cd_acordao}, strict_match=False)],
    )
    _registrar(cjsg.iloc[2].cd_acordao)

    with pytest.warns(BloqueioAntiBotWarning, match="2 download\\(s\\) de acórdão falharam"):
        resultado = tjce.baixar_acordaos(cjsg)

    assert resultado["caminho_acordao"].isna().tolist() == [False, True, True]
    assert resultado["motivo_falha"].tolist() == [None, "bloqueio_anti_bot", "bloqueio_anti_bot"]
    assert len(responses.calls) == 2


@responses.activate
def test_baixar_acordaos_corpo_comprimido_corrompido_vira_linha(tjce):
    """Antes, o ``ContentDecodingError`` interrompia o lote e as linhas baixadas se perdiam."""
    cjsg = _cjsg().head(3)
    _registrar(cjsg.iloc[0].cd_acordao)
    responses.add(
        responses.GET,
        URL,
        body=requests.exceptions.ContentDecodingError("gzip inválido"),
        match=[query_param_matcher({"cdAcordao": cjsg.iloc[1].cd_acordao}, strict_match=False)],
    )
    _registrar(cjsg.iloc[2].cd_acordao)

    with pytest.warns(UserWarning, match="resposta_inesperada"):
        resultado = tjce.baixar_acordaos(cjsg)

    assert resultado["caminho_acordao"].isna().tolist() == [False, True, False]
    assert resultado["motivo_falha"].tolist() == [None, "resposta_inesperada", None]


def test_baixar_acordaos_exige_as_colunas_dos_codigos(tjce):
    with pytest.raises(ValueError, match="cd_foro"):
        tjce.baixar_acordaos(_cjsg().drop(columns=["cd_foro"]))


@pytest.mark.integration
def test_baixar_acordao_ao_vivo(tmp_path):
    tjce = jus.scraper("tjce", download_path=str(tmp_path))
    linha = tjce.cjsg("dano moral", paginas=1).iloc[0]

    caminho = tjce.baixar_acordao(linha.cd_acordao, linha.cd_foro)

    assert Path(caminho).read_bytes().startswith(b"%PDF")
