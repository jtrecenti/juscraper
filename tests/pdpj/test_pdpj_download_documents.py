"""Contratos offline para :meth:`PdpjScraper.download_documents`.

Cobre dois caminhos: (1) ``base_df`` veio de :meth:`documentos` (uma
linha por documento, ja com ``id_documento`` exposto) e (2) ``base_df``
veio de :meth:`cpopg` (uma linha por processo com ``detalhes`` cheio).
"""
from __future__ import annotations

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.aggregators.pdpj.download import BASE_URL
from tests._helpers import load_sample

FAKE_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9."
)
PROC = "10029886420194014100"


def _mk_scraper():
    s = jus.scraper("pdpj", sleep_time=0)
    s.auth(FAKE_TOKEN)
    return s


def _mock_documentos_endpoint() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/{PROC}/documentos",
        body=load_sample("pdpj", "documentos/lista_normal.json"),
        status=200,
        content_type="application/json",
    )


def _mock_cpopg_endpoint() -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/{PROC}",
        body=load_sample("pdpj", "cpopg/processo_encontrado.json"),
        status=200,
        content_type="application/json",
    )


def _mock_text_endpoint(doc_id: str, body: str) -> None:
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/{PROC}/documentos/{doc_id}/texto",
        body=body,
        status=200,
        content_type="text/plain",
    )


@responses.activate
def test_download_documents_a_partir_de_documentos_df():
    _mock_documentos_endpoint()
    s = _mk_scraper()
    docs_df = s.documentos(PROC)
    assert not docs_df.empty

    # Mocka texto para todos os documentos retornados.
    for doc_id in docs_df["id_documento"]:
        _mock_text_endpoint(doc_id, f"texto do doc {doc_id}\n")

    out = s.download_documents(docs_df, with_text=True, with_binary=False)
    assert isinstance(out, pd.DataFrame)
    assert {"processo", "id_documento", "texto"} <= set(out.columns)
    assert len(out) == len(docs_df)
    assert all(out["texto"].str.startswith("texto do doc"))


@responses.activate
def test_download_documents_max_docs_per_process():
    _mock_documentos_endpoint()
    s = _mk_scraper()
    docs_df = s.documentos(PROC)
    # Mocka so o primeiro doc — se a respeito de max_docs_per_process funcionar,
    # so essa requisicao sera feita.
    primeiro = docs_df.iloc[0]["id_documento"]
    _mock_text_endpoint(primeiro, "primeiro\n")

    out = s.download_documents(docs_df, max_docs_per_process=1)
    assert len(out) == 1
    assert out.iloc[0]["id_documento"] == primeiro


@responses.activate
def test_download_documents_a_partir_de_cpopg_df():
    """Documentos podem vir aninhados em ``tramitacoes[*].documentos``."""
    _mock_cpopg_endpoint()
    s = _mk_scraper()
    cpopg_df = s.cpopg(PROC)
    detalhes = cpopg_df.iloc[0]["detalhes"]
    docs = list(detalhes.get("documentos") or [])
    for tram in detalhes.get("tramitacoes", []) or []:
        docs.extend(tram.get("documentos") or [])
    if not docs:
        # processo sem nenhum documento -> retorno vazio sem erro
        out = s.download_documents(cpopg_df)
        assert out.empty
        return
    for doc in docs:
        _mock_text_endpoint(doc["id"], f"texto:{doc['id']}")
    out = s.download_documents(cpopg_df)
    assert len(out) == len(docs)


@responses.activate
def test_download_documents_with_binary_baixa_bytes():
    _mock_documentos_endpoint()
    s = _mk_scraper()
    docs_df = s.documentos(PROC).head(1)
    doc_id = docs_df.iloc[0]["id_documento"]
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/{PROC}/documentos/{doc_id}/binario",
        body=b"\x89PNG\r\n",
        status=200,
        content_type="image/png",
    )
    out = s.download_documents(docs_df, with_text=False, with_binary=True)
    assert isinstance(out.iloc[0]["binario"], bytes)
    assert out.iloc[0]["binario"].startswith(b"\x89PNG")


def test_download_documents_exige_pelo_menos_um_modo():
    s = _mk_scraper()
    df = pd.DataFrame([{
        "processo": PROC,
        "id_documento": "abc",
        "numero_processo": PROC,
    }])
    with pytest.raises(ValueError, match="with_text.*with_binary"):
        s.download_documents(df, with_text=False, with_binary=False)


def test_download_documents_rejeita_df_sem_id_documento_ou_detalhes():
    s = _mk_scraper()
    df = pd.DataFrame([{"processo": PROC, "outra_coluna": 1}])
    with pytest.raises(ValueError, match="id_documento.*detalhes"):
        s.download_documents(df)


def test_download_documents_kwarg_desconhecido_raises_typeerror():
    s = _mk_scraper()
    df = pd.DataFrame([{
        "processo": PROC,
        "id_documento": "abc",
        "numero_processo": PROC,
    }])
    with pytest.raises(TypeError, match="parametro_inventado"):
        s.download_documents(df, parametro_inventado="x")
