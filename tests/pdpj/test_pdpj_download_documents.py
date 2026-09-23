"""Contratos offline para :meth:`PdpjScraper.download_documents`.

Cobre dois caminhos: (1) ``base_df`` veio de :meth:`documentos` (uma
linha por documento, ja com ``id_documento`` exposto) e (2) ``base_df``
veio de :meth:`cpopg` (uma linha por processo com ``detalhes`` cheio).
"""
from __future__ import annotations

import re

import pandas as pd
import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.aggregators.pdpj.download import BASE_URL
from tests._helpers import load_sample

FAKE_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9."
)
PROC = "10029886420194014100"
COERCED_DOCUMENT_COLUMNS = [
    "processo",
    "numero_processo",
    "id_documento",
    "id_codex",
    "sequencia",
    "data_juntada",
    "nome",
    "nivel_sigilo",
    "tipo_codigo",
    "tipo_nome",
    "arquivo_id",
    "arquivo_tipo",
    "arquivo_tamanho",
    "arquivo_paginas",
]


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


def _mock_any_text_endpoint() -> None:
    """Responde ao texto de qualquer documento, de qualquer processo."""
    responses.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE_URL)}/processos/[^/]+/documentos/[^/]+/texto"),
        body="texto qualquer\n",
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
def test_download_documents_limite_zero_nao_faz_requisicao():
    s = _mk_scraper()
    docs_df = pd.DataFrame([
        {"processo": PROC, "numero_processo": PROC, "id_documento": "doc-1"},
        {"processo": PROC, "numero_processo": PROC, "id_documento": "doc-2"},
    ])

    out = s.download_documents(docs_df, max_docs_per_process=0)

    assert isinstance(out, pd.DataFrame)
    assert out.empty
    assert len(responses.calls) == 0


@responses.activate
def test_download_documents_usa_valores_coeridos_pelo_schema():
    _mock_documentos_endpoint()
    s = _mk_scraper()
    docs_df = s.documentos(PROC)
    primeiro = docs_df.iloc[0]["id_documento"]
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/{PROC}/documentos/{primeiro}/binario",
        body=b"conteudo-binario",
        status=200,
        content_type="application/octet-stream",
    )

    out = s.download_documents(
        docs_df,
        max_docs_per_process="1",
        with_text="false",
        with_binary="true",
    )

    assert out["id_documento"].tolist() == [primeiro]
    assert out.iloc[0]["binario"] == b"conteudo-binario"
    assert "texto" not in out.columns


@responses.activate
def test_download_documents_coage_with_binary_falso_em_string():
    """``with_binary="false"`` e truthy em Python; so o schema o torna ``False``."""
    _mock_documentos_endpoint()
    s = _mk_scraper()
    docs_df = s.documentos(PROC)
    for doc_id in docs_df["id_documento"]:
        _mock_text_endpoint(doc_id, f"texto do doc {doc_id}\n")
    responses.calls.reset()

    out = s.download_documents(docs_df, with_text=True, with_binary="false")

    assert "binario" not in out.columns
    assert "texto" in out.columns
    assert len(responses.calls) == len(docs_df)


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
    with pytest.raises(ValueError, match=r"with_text.*with_binary"):
        s.download_documents(df, with_text=False, with_binary=False)


def test_download_documents_rejeita_df_sem_id_documento_ou_detalhes():
    s = _mk_scraper()
    df = pd.DataFrame([{"processo": PROC, "outra_coluna": 1}])
    with pytest.raises(
        ValueError,
        match=r"base_df precisa ter coluna 'id_documento'.*ou 'detalhes'",
    ):
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


@pytest.mark.parametrize("base_df", [None, []])
def test_download_documents_rejeita_base_que_nao_e_dataframe(base_df):
    s = _mk_scraper()

    with pytest.raises(ValidationError, match="base_df"):
        s.download_documents(base_df)


def test_download_documents_rejeita_limite_negativo():
    s = _mk_scraper()

    with pytest.raises(ValidationError, match="max_docs_per_process"):
        s.download_documents(
            pd.DataFrame([{"processo": PROC, "id_documento": "doc-1"}]),
            max_docs_per_process=-1,
        )


@responses.activate
def test_download_documents_ignora_detalhes_nao_dict_e_listas_vazias():
    _mock_any_text_endpoint()
    s = _mk_scraper()
    base_df = pd.DataFrame([
        {"processo": "processo-1", "detalhes": None},
        {"processo": "processo-2", "detalhes": "malformado"},
        {"processo": "processo-3", "detalhes": ["malformado"]},
        {
            "processo": "processo-4",
            "detalhes": {"documentos": None, "tramitacoes": []},
        },
        {
            "processo": "processo-5",
            "detalhes": {"documentos": [], "tramitacoes": None},
        },
        {
            "processo": "processo-6",
            "detalhes": {"documentos": "lista-malformada", "tramitacoes": [42]},
        },
    ])

    out = s.download_documents(base_df)

    assert out.empty
    assert len(responses.calls) == 0


@responses.activate
def test_download_documents_preserva_precedencia_ordem_duplicatas_e_shape():
    _mock_any_text_endpoint()
    s = _mk_scraper()
    top_document = {
        "id": "doc-top",
        "idCodex": "codex-top",
        "sequencia": 1,
        "dataHoraJuntada": "2026-01-02T03:04:05",
        "nome": "Documento do topo",
        "nivelSigilo": 0,
        "tipo": {"codigo": 10, "nome": "Petição"},
        "arquivo": {
            "id": "arquivo-top",
            "tipo": "application/pdf",
            "tamanho": 123,
            "quantidadePaginas": 2,
        },
    }
    nested_document = {
        "id": "doc-tramitacao",
        "tipo": None,
        "arquivo": None,
    }
    last_document = {"id": "doc-ultima-linha"}
    base_df = pd.DataFrame([
        {
            "processo": "cnj-pesquisado-1",
            "detalhes": {
                "numeroProcesso": "cnj-retornado-1",
                "documentos": [top_document, "documento-malformado", top_document],
                "tramitacoes": [
                    None,
                    {"documentos": []},
                    {"documentos": [nested_document, 42, top_document]},
                    {"documentos": None},
                    {"documentos": "lista-malformada"},
                    "tramitacao-malformada",
                ],
            },
        },
        {
            "processo": "cnj-pesquisado-2",
            "detalhes": {
                "numeroProcesso": "cnj-retornado-2",
                "documentos": [last_document],
            },
        },
    ])

    out = s.download_documents(base_df)

    assert out.columns.tolist() == [*COERCED_DOCUMENT_COLUMNS, "texto", "_raw_texto"]
    assert out["id_documento"].tolist() == [
        "doc-top",
        "doc-top",
        "doc-tramitacao",
        "doc-top",
        "doc-ultima-linha",
    ]
    assert out["processo"].tolist() == [
        "cnj-pesquisado-1",
        "cnj-pesquisado-1",
        "cnj-pesquisado-1",
        "cnj-pesquisado-1",
        "cnj-pesquisado-2",
    ]
    assert len(responses.calls) == 5
    # As colunas numericas viram float porque outras linhas trazem None;
    # a comparacao por igualdade aceita 1 == 1.0 sem fixar o dtype.
    primeira = out.iloc[0]
    assert {coluna: primeira[coluna] for coluna in COERCED_DOCUMENT_COLUMNS} == {
        "processo": "cnj-pesquisado-1",
        "numero_processo": "cnj-retornado-1",
        "id_documento": "doc-top",
        "id_codex": "codex-top",
        "sequencia": 1,
        "data_juntada": "2026-01-02T03:04:05",
        "nome": "Documento do topo",
        "nivel_sigilo": 0,
        "tipo_codigo": 10,
        "tipo_nome": "Petição",
        "arquivo_id": "arquivo-top",
        "arquivo_tipo": "application/pdf",
        "arquivo_tamanho": 123,
        "arquivo_paginas": 2,
    }
