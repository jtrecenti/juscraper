"""Offline contract tests for JusbrScraper.download_documents.

Fluxo real do ``download_documents`` (de ``aggregators/jusbr/client.py``):

1. Para cada linha em ``base_df``: extrai ``numeroProcesso``, ``detalhes``.
2. Caminha por ``detalhes['dadosBasicos']['documentos']`` (com fallbacks em
   ``detalhes['documentos']`` e ``detalhes['tramitacaoAtual']['documentos']``).
3. Para cada documento, extrai UUID de ``hrefTexto`` e ``hrefBinario``
   independentes. Followup 3 da #141: documento so e pulado quando **os
   dois** UUIDs faltam; com qualquer um valido, baixa o que da:
   - so ``hrefTexto`` -> linha com ``texto`` preenchido e
     ``_raw_binary_api == None``.
   - so ``hrefBinario`` -> linha com ``texto == None`` e
     ``_raw_binary_api`` preenchido.
4. URLs:
   - texto em ``api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/...``
   - binario em ``portaldeservicos.pdpj.jus.br/api/v2/...`` (NAO data-lake)
5. Linha de saida tem ``numero_processo``, ``texto``, ``_raw_text_api``,
   ``_raw_binary_api`` + todos os campos do ``doc_meta``.

Samples (``text_typical.txt`` / ``binary_typical.bin``) sao capturados via
``tests/fixtures/capture/jusbr.py``.
"""
import jwt
import pandas as pd
import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample, load_sample_bytes

BASE_TEXT_URL = "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos"
BASE_BINARY_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos"
HMAC_KEY = "0123456789abcdef0123456789abcdef-test"

CNJ_DIGITS = "00000000000000000000"
UUID_TEXT_1 = "11111111-1111-1111-1111-111111111111"
UUID_BIN_1 = "22222222-2222-2222-2222-222222222222"
UUID_TEXT_2 = "33333333-3333-3333-3333-333333333333"
UUID_BIN_2 = "44444444-4444-4444-4444-444444444444"


def _fake_jwt() -> str:
    encoded: str = jwt.encode({"sub": "tester", "exp": 9999999999}, HMAC_KEY, algorithm="HS256")
    return encoded


def _authenticated_scraper(sleep_time: float = 0.0):
    scraper = jus.scraper("jusbr", sleep_time=sleep_time)
    scraper.auth(_fake_jwt())
    return scraper


def _doc_meta(*, href_texto: str | None, href_binario: str | None, **extra) -> dict:
    """Build a documento metadata dict like the PDPJ ``dadosBasicos.documentos`` items."""
    meta = {
        "idDocumento": extra.get("idDocumento", "doc-id-1"),
        "sequencia": extra.get("sequencia", 1),
        "descricao": extra.get("descricao", "Peticao Inicial"),
        "tipo": extra.get("tipo", "PETICAO"),
    }
    if href_texto is not None:
        meta["hrefTexto"] = href_texto
    if href_binario is not None:
        meta["hrefBinario"] = href_binario
    return meta


def _base_df(documentos: list[dict]) -> pd.DataFrame:
    """Build the input DataFrame for ``download_documents``."""
    return pd.DataFrame([{
        "processo_pesquisado": CNJ_DIGITS,
        "numeroProcesso": CNJ_DIGITS,
        "processo": CNJ_DIGITS,
        "idCodexTribunal": "TRIB",
        "detalhes": {"dadosBasicos": {"documentos": documentos}},
    }])


def _href_texto(uuid: str) -> str:
    return f"/processos/{CNJ_DIGITS}/documentos/{uuid}/texto"


def _href_binario(uuid: str) -> str:
    return f"/processos/{CNJ_DIGITS}/documentos/{uuid}/binario"


@responses.activate(registry=OrderedRegistry)
def test_download_documents_baixa_texto_e_binario(mocker):
    """``hrefTexto`` + ``hrefBinario`` -> texto + binario na linha de saida."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.columns[0] == "numero_processo"
    assert df.iloc[0]["numero_processo"] == CNJ_DIGITS
    assert isinstance(df.iloc[0]["texto"], str) and len(df.iloc[0]["texto"]) > 0
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)
    assert len(df.iloc[0]["_raw_binary_api"]) > 0


@responses.activate(registry=OrderedRegistry)
def test_download_documents_sem_href_binario_baixa_so_texto(mocker):
    """Sem ``hrefBinario``: linha com ``texto`` populado e ``_raw_binary_api == None``.

    Followup 3 da #141: download parcial em vez de skip.
    """
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=None),
    ])

    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert isinstance(df.iloc[0]["texto"], str) and len(df.iloc[0]["texto"]) > 0
    assert df.iloc[0]["_raw_binary_api"] is None


@responses.activate(registry=OrderedRegistry)
def test_download_documents_sem_href_texto_baixa_so_binario(mocker):
    """Sem ``hrefTexto``: linha com ``_raw_binary_api`` populado e ``texto == None``."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=None, href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["texto"] is None
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)
    assert len(df.iloc[0]["_raw_binary_api"]) > 0


@responses.activate(registry=OrderedRegistry)
def test_download_documents_href_texto_malformado_baixa_so_binario(mocker):
    """``hrefTexto`` sem ``/documentos/`` -> sem UUID de texto -> baixa so binario."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto="/path/sem/marcador", href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["texto"] is None
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)


@responses.activate(registry=OrderedRegistry)
def test_download_documents_ambos_hrefs_ausentes_pula_documento(mocker):
    """Sem ``hrefTexto`` nem ``hrefBinario`` -> documento pulado, sem HTTP."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=None, href_binario=None),
    ])

    df = scraper.download_documents(base_df)
    # Nenhum responses.add — o teste tambem confirma que nenhum HTTP saiu.
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_download_documents_max_docs_per_process_limita(mocker):
    """``max_docs_per_process=1`` com 2 docs -> baixa apenas o primeiro."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(
            href_texto=_href_texto(UUID_TEXT_1),
            href_binario=_href_binario(UUID_BIN_1),
            idDocumento="doc-1",
            sequencia=1,
        ),
        _doc_meta(
            href_texto=_href_texto(UUID_TEXT_2),
            href_binario=_href_binario(UUID_BIN_2),
            idDocumento="doc-2",
            sequencia=2,
        ),
    ])

    # So registramos os mocks do PRIMEIRO documento. Se o codigo ignorasse
    # ``max_docs_per_process``, a request do 2o doc bateria sem mock e o
    # ``responses.activate`` falharia o teste.
    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df, max_docs_per_process=1)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["idDocumento"] == "doc-1"


def test_download_documents_sem_auth_levanta_runtime_error():
    """Sem ``auth(token)`` previo, ``download_documents`` aborta antes do loop."""
    scraper = jus.scraper("jusbr")
    base_df = _base_df([_doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=_href_binario(UUID_BIN_1))])
    with pytest.raises(RuntimeError, match="[Aa]utentica"):
        scraper.download_documents(base_df)
