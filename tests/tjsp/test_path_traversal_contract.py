"""Contratos de seguranca: path traversal via identificadores upstream (refs #269).

Os tres downloaders do TJSP interpolavam um identificador vindo da resposta do
tribunal (``cdProcesso``, ``processo.codigo``, ``cdAcordao``) direto no caminho
de escrita. Estes testes alimentam um identificador malicioso (``../../evil``) e
afirmam que o downloader levanta ``ValueError`` antes de gravar fora do diretorio
de download — em vez de permitir escrita arbitraria de arquivo.

Os corpos de resposta sao construidos inline (entrada adversarial), nao como
samples versionados, porque nao representam markup/JSON real do TJSP.
"""
import json

import pytest
import responses

import juscraper as jus
from juscraper.courts.tjsp.acordao_download import download_acordao
from juscraper.courts.tjsp.cpopg_download import cpopg_download_api, cpopg_download_api_single
from juscraper.courts.tjsp.cposg_download import _cposg_download_html_single

ESAJ = "https://esaj.tjsp.jus.br"
API = "https://api.tjsp.jus.br"

CNJ = "1000149-71.2024.8.26.0346"
CNJ_DIGITS = "10001497120248260346"
EVIL = "../../evil"


# ---------- cpopg (API) -------------------------------------------------

@responses.activate
def test_cpopg_api_rejeita_cdprocesso_malicioso(tmp_path, mocker):
    """cdProcesso com '..' levanta ValueError antes do POST dadosbasicos."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body=json.dumps([{"cdProcesso": EVIL}]),
        status=200,
        content_type="application/json",
    )

    with pytest.raises(ValueError, match="cdProcesso"):
        cpopg_download_api_single(CNJ, scraper.session, scraper.api_base, str(tmp_path))

    # nenhum *_basicos.json gravado (nem dentro nem fora do diretorio cpopg/<id>)
    assert not list(tmp_path.rglob("*_basicos.json"))
    assert not (tmp_path / "evil_basicos.json").exists()


@responses.activate
def test_cpopg_api_caller_captura_e_continua(tmp_path, mocker):
    """O caller cpopg_download_api captura o ValueError e nao propaga."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    responses.add(
        responses.GET,
        f"{API}/processo/cpopg/search/numproc/{CNJ_DIGITS}",
        body=json.dumps([{"cdProcesso": EVIL}]),
        status=200,
        content_type="application/json",
    )

    # nao deve levantar — loga o erro e segue para o proximo id
    cpopg_download_api([CNJ], scraper.session, scraper.api_base, str(tmp_path))

    assert not list(tmp_path.rglob("*_basicos.json"))


# ---------- cposg (HTML) ------------------------------------------------

_LISTAGEM_MALICIOSA = (
    '<html><body><div id="listagemDeProcessos">'
    f'<a class="linkProcesso" href="/cposg/show.do?processo.codigo={EVIL}">proc</a>'
    '</div></body></html>'
)


@responses.activate
def test_cposg_html_rejeita_codigo_malicioso(tmp_path, mocker):
    """processo.codigo com '..' levanta ValueError antes do GET show.do."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    responses.add(
        responses.GET, f"{ESAJ}/cposg/open.do",
        body="<html></html>", status=200, content_type="text/html",
    )
    responses.add(
        responses.GET, f"{ESAJ}/cposg/search.do",
        body=_LISTAGEM_MALICIOSA, status=200, content_type="text/html",
    )

    with pytest.raises(ValueError, match="processo.codigo"):
        _cposg_download_html_single(CNJ, scraper.session, scraper.u_base, str(tmp_path))

    # nenhum HTML de processo gravado
    assert not list(tmp_path.rglob("*.html"))


# ---------- acordao -----------------------------------------------------

@responses.activate
def test_acordao_rejeita_cd_acordao_malicioso(tmp_path):
    """cdAcordao com '..' levanta ValueError (codigo morto, mas o defeito e real)."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    responses.add(responses.GET, f"{ESAJ}/cjsg/getArquivo.do", body=b"%PDF-fake", status=200)

    with pytest.raises(ValueError, match="cdAcordao"):
        download_acordao(EVIL, scraper.session, ESAJ, str(tmp_path))

    assert not list(tmp_path.rglob("*.pdf"))


@responses.activate
def test_acordao_happy_path(tmp_path):
    """cdAcordao numerico legitimo grava em cjsg/<id>.pdf normalmente."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    responses.add(responses.GET, f"{ESAJ}/cjsg/getArquivo.do", body=b"%PDF-fake", status=200)

    download_acordao("12345", scraper.session, ESAJ, str(tmp_path))

    assert (tmp_path / "cjsg" / "12345.pdf").exists()
