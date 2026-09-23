"""Granular characterization tests for the TJPR CJSG parser."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import requests

from juscraper.courts.tjpr.parse import cjsg_parse
from tests._helpers import load_sample

EXPECTED_COLUMNS = ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]
TRUNCATED_WITH_ID = "Resumo truncado. Leia mais..."
TRUNCATED_WITHOUT_INPUT = "Resumo sem id documental. Leia mais..."
TRUNCATED_WITHOUT_VALUE = "Resumo com id sem valor. Leia mais..."


def test_cjsg_parse_preserves_row_variants_and_exact_dtypes(mocker):
    request_fn = mocker.Mock()

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio=None,
        request_fn=request_fn,
    )

    assert result.columns.tolist() == EXPECTED_COLUMNS
    assert result.dtypes.astype(str).to_dict() == dict.fromkeys(EXPECTED_COLUMNS, "object")
    assert result.shape == (5, 5)
    assert result.loc[0].to_dict() == {
        "processo": "0000001-11.2024.8.16.0001",
        "orgao_julgador": "Câmara Inline",
        "relator": "Relator Inline",
        "data_julgamento": date(2024, 2, 1),
        "ementa": "Ementa curta sem expansão.",
    }
    assert result.loc[1].to_dict() == {
        "processo": "0000002-22.2024.8.16.0002",
        "orgao_julgador": "Câmara Irmã",
        "relator": "Relator Irmão",
        "data_julgamento": date(2024, 4, 3),
        "ementa": TRUNCATED_WITH_ID,
    }
    assert result.loc[2, ["processo", "orgao_julgador", "relator"]].tolist() == ["", "", ""]
    assert pd.isna(result.loc[2, "data_julgamento"])
    assert result.loc[2, "ementa"] == "Ementa sem metadados."
    assert result.loc[3].to_dict() == {
        "processo": "0000003-33.2024.8.16.0003",
        "orgao_julgador": "Câmara Sem Id",
        "relator": "Relator Sem Id",
        "data_julgamento": date(2024, 6, 5),
        "ementa": TRUNCATED_WITHOUT_INPUT,
    }
    assert result.loc[4].to_dict() == {
        "processo": "0000004-44.2024.8.16.0004",
        "orgao_julgador": "Câmara Id Vazio",
        "relator": "Relator Id Vazio",
        "data_julgamento": date(2024, 8, 7),
        "ementa": TRUNCATED_WITHOUT_VALUE,
    }
    request_fn.assert_not_called()


def test_cjsg_parse_keeps_truncated_ementa_without_request_fn():
    # Com critério e sem request_fn, o parse offline não tenta buscar a ementa completa.
    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio="dano moral",
    )

    assert result.shape == (5, 5)
    assert result.loc[1, "ementa"] == TRUNCATED_WITH_ID
    assert result.loc[3, "ementa"] == TRUNCATED_WITHOUT_INPUT
    assert result.loc[4, "ementa"] == TRUNCATED_WITHOUT_VALUE


def test_cjsg_parse_fetches_full_ementa_with_injected_request(mocker):
    request_fn = mocker.Mock(
        return_value=SimpleNamespace(text="<div>Ementa completa</div><p>Segunda linha</p>")
    )

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio="dano moral",
        request_fn=request_fn,
    )

    assert result.loc[0, "ementa"] == "Ementa curta sem expansão."
    assert result.loc[1, "ementa"] == "Ementa completa\nSegunda linha"
    # Linhas com "Leia mais..." sem id documental utilizável ficam truncadas, sem requisição.
    assert result.loc[3, "ementa"] == TRUNCATED_WITHOUT_INPUT
    assert result.loc[4, "ementa"] == TRUNCATED_WITHOUT_VALUE
    request_fn.assert_called_once()
    method, url = request_fn.call_args.args
    assert method == "GET"
    assert parse_qs(urlsplit(url).query) == {
        "actionType": ["exibirTextoCompleto"],
        "idProcesso": ["div-id"],
        "criterio": ["dano moral"],
    }


def test_cjsg_parse_keeps_truncated_ementa_after_row_request_error(mocker):
    request_fn = mocker.Mock(side_effect=requests.RequestException("indisponível"))

    result = cjsg_parse(
        [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
        criterio="dano moral",
        request_fn=request_fn,
    )

    assert result.loc[1, "ementa"] == (
        f"{TRUNCATED_WITH_ID}\n"
        "[Erro ao buscar ementa completa: indisponível]"
    )
    assert result.loc[2, "ementa"] == "Ementa sem metadados."
    assert result.loc[3, "ementa"] == TRUNCATED_WITHOUT_INPUT
    assert result.loc[4, "ementa"] == TRUNCATED_WITHOUT_VALUE
    request_fn.assert_called_once()


def test_cjsg_parse_propagates_programming_errors_from_full_ementa_fetch(mocker):
    request_fn = mocker.Mock(side_effect=AttributeError("contrato inválido"))

    with pytest.raises(AttributeError, match="contrato inválido"):
        cjsg_parse(
            [load_sample("tjpr", "cjsg/parser_edge_cases.html")],
            criterio="dano moral",
            request_fn=request_fn,
        )
