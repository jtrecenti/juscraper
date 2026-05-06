"""Contratos offline para o agregador PDPJ.

Cada teste mocka o endpoint REST GET correspondente via :mod:`responses`
e valida o shape do DataFrame produzido. Os samples vivem em
``tests/pdpj/samples/`` e foram capturados contra a API real
(``api-processo-integracao.data-lake.pdpj.jus.br``) com um JWT valido.
"""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.aggregators.pdpj.client import _to_query_params
from juscraper.aggregators.pdpj.download import BASE_URL
from juscraper.aggregators.pdpj.parse import (
    build_documento_rows,
    build_movimento_rows,
    build_parte_rows,
    build_processo_row,
    clean_document_text,
    parse_pesquisa_response,
)
from tests._helpers import (
    assert_unknown_kwarg_raises,
    load_sample,
    query_param_subset_matcher,
)

# Token JWT minimo (header + payload com ``exp`` futura) so para passar pelo
# decoder do PyJWT em ``PdpjScraper.auth``. Nao bate com nenhuma chave real --
# os testes mockam a rede e nunca enviam ele para fora.
FAKE_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9."
)


def _mk_scraper():
    s = jus.scraper("pdpj", sleep_time=0)
    s.auth(FAKE_TOKEN)
    return s


# ---------------------------------------------------------------------
# existe
# ---------------------------------------------------------------------

@responses.activate
def test_existe_str_returns_bool():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100/existe",
        body="true",
        status=200,
        content_type="application/json",
    )
    out = _mk_scraper().existe("10029886420194014100")
    assert out is True


@responses.activate
def test_existe_list_returns_dataframe():
    for cnj, body in [
        ("10029886420194014100", "true"),
        ("00000000000000000000", "false"),
    ]:
        responses.add(
            responses.GET,
            f"{BASE_URL}/processos/{cnj}/existe",
            body=body, status=200, content_type="application/json",
        )
    df = _mk_scraper().existe(["10029886420194014100", "00000000000000000000"])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["processo", "existe"]
    assert bool(df.iloc[0]["existe"]) is True
    assert bool(df.iloc[1]["existe"]) is False


def test_existe_requires_auth():
    s = jus.scraper("pdpj")
    with pytest.raises(RuntimeError, match="Autenticacao necessaria"):
        s.existe("10029886420194014100")


# ---------------------------------------------------------------------
# cpopg
# ---------------------------------------------------------------------

CPOPG_REQUIRED_COLUMNS = {
    "processo",
    "numero_processo",
    "id",
    "sigla_tribunal",
    "segmento_justica",
    "data_atualizacao",
    "detalhes",
}


@responses.activate
def test_cpopg_processo_encontrado():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100",
        body=load_sample("pdpj", "cpopg/processo_encontrado.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().cpopg("10029886420194014100")
    assert isinstance(df, pd.DataFrame)
    assert CPOPG_REQUIRED_COLUMNS <= set(df.columns)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["processo"] == "10029886420194014100"
    assert row["sigla_tribunal"] == "TRF1"
    assert isinstance(row["detalhes"], dict)


@responses.activate
def test_cpopg_processo_nao_encontrado():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/00000000000000000000",
        body=load_sample("pdpj", "cpopg/processo_nao_encontrado.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().cpopg("00000000000000000000")
    assert len(df) == 1
    assert df.iloc[0]["status_consulta"] == "Nao encontrado"
    assert df.iloc[0]["detalhes"] is None


@responses.activate
def test_cpopg_aceita_lista_e_normaliza_cnj():
    """Cnj com mascara e digitos extras deve ser limpo antes de virar URL."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100",
        body=load_sample("pdpj", "cpopg/processo_encontrado.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().cpopg(["1002988-64.2019.4.01.4100"])
    assert len(df) == 1
    assert df.iloc[0]["processo"] == "10029886420194014100"


# ---------------------------------------------------------------------
# documentos / movimentos / partes
# ---------------------------------------------------------------------

@responses.activate
def test_documentos_lista_normal():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100/documentos",
        body=load_sample("pdpj", "documentos/lista_normal.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().documentos("10029886420194014100")
    assert {"processo", "id_documento", "nome", "tipo_nome", "arquivo_id"} <= set(df.columns)
    assert len(df) > 0
    # id_documento deve ser UUID
    assert df.iloc[0]["id_documento"]
    assert re.match(r"^[0-9a-f]{8}-", str(df.iloc[0]["id_documento"]))


@responses.activate
def test_documentos_lista_vazia():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/00000000000000000000/documentos",
        body=load_sample("pdpj", "documentos/lista_vazia.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().documentos("00000000000000000000")
    assert df.empty


@responses.activate
def test_movimentos_lista_normal():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100/movimentos",
        body=load_sample("pdpj", "movimentos/lista_normal.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().movimentos("10029886420194014100")
    assert {"processo", "sequencia", "data_hora", "descricao", "tipo_nome"} <= set(df.columns)
    assert len(df) > 0


@responses.activate
def test_partes_lista_normal():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos/10029886420194014100/partes",
        body=load_sample("pdpj", "partes/lista_normal.json"),
        status=200,
        content_type="application/json",
    )
    df = _mk_scraper().partes("10029886420194014100")
    assert {"processo", "polo", "tipo_parte", "nome", "tipo_pessoa"} <= set(df.columns)
    assert len(df) > 0


# ---------------------------------------------------------------------
# pesquisa / contar
# ---------------------------------------------------------------------

@responses.activate
def test_pesquisa_single_page():
    sample = load_sample("pdpj", "pesquisa/single_page.json")
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        body=sample,
        status=200,
        content_type="application/json",
        match=[query_param_subset_matcher({
            "numeroProcesso": "10029886420194014100",
        })],
    )
    df = _mk_scraper().pesquisa(numero_processo="10029886420194014100", paginas=1)
    assert {"numero_processo", "id", "sigla_tribunal"} <= set(df.columns)
    assert len(df) == 1


@responses.activate
def test_pesquisa_lista_orgao_julgador_vira_csv():
    """``id_orgao_julgador=[1, 2]`` deve virar ``"1,2"`` na querystring."""
    captured: dict[str, str] = {}

    def _matcher(request):
        qs = parse_qs(urlparse(request.url).query, keep_blank_values=True)
        captured["idOrgaoJulgador"] = qs.get("idOrgaoJulgador", [None])[0]
        return True, ""

    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        json={"total": 0, "content": [], "searchAfter": None},
        status=200,
        match=[_matcher],
    )
    _mk_scraper().pesquisa(id_orgao_julgador=["12345", "67890"], paginas=1)
    assert captured["idOrgaoJulgador"] == "12345,67890"


@responses.activate
def test_pesquisa_kwarg_desconhecido_raises_typeerror():
    s = _mk_scraper()
    assert_unknown_kwarg_raises(s.pesquisa, "parametro_inventado", paginas=1)


@responses.activate
def test_contar_returns_int():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos:contar",
        body="42",
        status=200,
        content_type="application/json",
    )
    total = _mk_scraper().contar(numero_processo="10029886420194014100")
    assert total == 42


@responses.activate
def test_contar_aceita_resposta_json_dict():
    """Algumas versoes da API embrulham o total em ``{"total": N}``."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos:contar",
        json={"total": 7},
        status=200,
    )
    assert _mk_scraper().contar(tribunal="TRF1") == 7


# ---------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------

def test_auth_token_invalido_raises_valueerror():
    s = jus.scraper("pdpj")
    with pytest.raises(ValueError, match="Token JWT invalido"):
        s.auth("not-a-jwt")


def test_auth_define_header_authorization():
    s = jus.scraper("pdpj")
    assert "Authorization" not in s.session.headers
    s.auth(FAKE_TOKEN)
    assert s.session.headers["Authorization"] == f"Bearer {FAKE_TOKEN}"


# ---------------------------------------------------------------------
# parse module: testes granulares (sem rede)
# ---------------------------------------------------------------------

def test_build_processo_row_extrai_top_level_e_mantem_detalhes_completos():
    sample = json.loads(load_sample("pdpj", "cpopg/processo_encontrado.json"))[0]
    row = build_processo_row(sample, "10029886420194014100")
    assert row["processo"] == "10029886420194014100"
    assert row["sigla_tribunal"] == sample["siglaTribunal"]
    assert row["detalhes"] is sample


def test_build_documento_rows_achata_arquivo_e_tipo():
    sample = json.loads(load_sample("pdpj", "documentos/lista_normal.json"))
    rows = build_documento_rows(sample, "10029886420194014100")
    assert len(rows) == len(sample["documentos"])
    primeiro = rows[0]
    assert primeiro["arquivo_id"] is not None
    assert primeiro["tipo_codigo"] is not None


def test_build_movimento_rows_achata_classe_e_tipo():
    sample = json.loads(load_sample("pdpj", "movimentos/lista_normal.json"))
    rows = build_movimento_rows(sample, "10029886420194014100")
    assert len(rows) == len(sample["movimentos"])
    assert all("classe_codigo" in r for r in rows)


def test_build_parte_rows_extrai_documento_principal():
    sample = json.loads(load_sample("pdpj", "partes/lista_normal.json"))
    rows = build_parte_rows(sample, "10029886420194014100")
    assert all("documento_numero" in r for r in rows)


def test_parse_pesquisa_response_extrai_search_after():
    sample = json.loads(load_sample("pdpj", "pesquisa/single_page.json"))
    rows, search_after, total = parse_pesquisa_response(sample)
    assert len(rows) == 1
    assert search_after == sample["searchAfter"]
    assert total == sample["total"]


def test_parse_pesquisa_response_lida_com_none():
    rows, search_after, total = parse_pesquisa_response(None)
    assert rows == []
    assert search_after is None
    assert total is None


def test_clean_document_text_remove_caracteres_de_controle():
    txt = "abc\x00def\x1aghi\r\njkl mno"
    assert clean_document_text(txt) == "abcdefghi\njkl\nmno"


def test_clean_document_text_string_vazia_retorna_none():
    assert clean_document_text("") is None
    assert clean_document_text(None) is None


def test_to_query_params_filtra_none_e_serializa_lista():
    params = _to_query_params({
        "numero_processo": "10029886420194014100",
        "id_orgao_julgador": ["12345", "67890"],
        "tribunal": None,
    })
    assert params == {
        "numeroProcesso": "10029886420194014100",
        "idOrgaoJulgador": "12345,67890",
    }
