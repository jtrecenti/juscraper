"""Caracteriza a paginação ``search_after`` do DataJud (refs #315)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd
import pytest

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client


def _page(page: int, *, size: int = 10, include_sort: bool = True) -> dict[str, Any]:
    hits = []
    for item in range(size):
        hit: dict[str, Any] = {
            "_source": {
                "numeroProcesso": f"{page:02d}-{item:02d}",
                "pagina_fisica": page,
            },
        }
        if include_sort:
            hit["sort"] = [f"cursor-{page:02d}-{item:02d}"]
        hits.append(hit)
    return {
        "hits": {
            "total": {"value": 1000, "relation": "eq"},
            "hits": hits,
        },
    }


def _install_pages(monkeypatch, pages: Iterable[dict[str, Any] | None]):
    calls: list[dict[str, Any]] = []
    responses = iter(pages)

    def fake_call(**kwargs):
        calls.append(kwargs)
        return next(responses)

    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
    monkeypatch.setattr(datajud_client.time, "sleep", lambda _: None)
    return calls


def _assert_cursor_chain(calls: list[dict[str, Any]]) -> None:
    assert "search_after" not in calls[0]["query_payload"]
    for page, call in enumerate(calls[1:], start=1):
        assert call["query_payload"]["search_after"] == [f"cursor-{page:02d}-09"]


def test_range_com_inicio_maior_percorre_prefixo_e_descarta(monkeypatch):
    calls = _install_pages(monkeypatch, [_page(page) for page in range(1, 6)])

    df = jus.scraper("datajud", verbose=0).listar_processos(
        tribunal="TJSP",
        paginas=range(3, 6),
        tamanho_pagina=10,
    )

    assert df["pagina_fisica"].tolist() == [3] * 10 + [4] * 10 + [5] * 10
    assert len(calls) == 5
    _assert_cursor_chain(calls)


def test_range_com_passo_retorna_apenas_paginas_pedidas(monkeypatch):
    calls = _install_pages(monkeypatch, [_page(page) for page in range(1, 5)])

    df = jus.scraper("datajud", verbose=0).listar_processos(
        tribunal="TJSP",
        paginas=range(2, 6, 2),
        tamanho_pagina=10,
    )

    assert df["pagina_fisica"].tolist() == [2] * 10 + [4] * 10
    assert len(calls) == 4
    _assert_cursor_chain(calls)


def test_lista_esparsa_continua_baixando_intervalo_inteiro(monkeypatch):
    calls = _install_pages(monkeypatch, [_page(page) for page in range(1, 6)])

    df = jus.scraper("datajud", verbose=0).listar_processos(
        tribunal="TJSP",
        paginas=[3, 5],
        tamanho_pagina=10,
    )

    assert df["pagina_fisica"].tolist() == [3] * 10 + [4] * 10 + [5] * 10
    assert len(calls) == 5


def test_falha_posterior_retorna_resultados_parciais(monkeypatch):
    calls = _install_pages(monkeypatch, [_page(1), None])

    with pytest.warns(UserWarning, match="página 2.*Resultados parciais"):
        df = jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP",
            paginas=range(1, 4),
            tamanho_pagina=10,
        )

    assert df["pagina_fisica"].tolist() == [1] * 10
    assert len(calls) == 2


def test_size_reduzido_fica_sticky_nas_paginas_seguintes(monkeypatch):
    calls: list[dict[str, Any]] = []

    def fake_call(**kwargs):
        calls.append(kwargs)
        payload = kwargs["query_payload"]
        if len(calls) == 1:
            payload["size"] = 100
            return _page(1, size=100)
        assert payload["size"] == 100
        return _page(2, size=1)

    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
    monkeypatch.setattr(datajud_client.time, "sleep", lambda _: None)

    df = jus.scraper("datajud", verbose=0).listar_processos(
        tribunal="TJSP",
        paginas=range(1, 3),
        tamanho_pagina=400,
    )

    assert len(df) == 101
    assert [call["query_payload"]["size"] for call in calls] == [100, 100]


def test_lista_de_cnjs_usa_alias_e_filtro_especificos(monkeypatch):
    calls = _install_pages(monkeypatch, [_page(1, size=1), _page(1, size=1)])
    cnj_tjac = "00033258820148010001"
    cnj_tjsp = "01234567820238260001"

    df = jus.scraper("datajud", verbose=0).listar_processos(
        numero_processo=[cnj_tjac, cnj_tjsp],
        paginas=1,
        tamanho_pagina=10,
    )

    assert isinstance(df, pd.DataFrame)
    assert [call["alias"] for call in calls] == ["api_publica_tjac", "api_publica_tjsp"]
    filters = [
        call["query_payload"]["query"]["bool"]["must"][0]["terms"]["numeroProcesso"]
        for call in calls
    ]
    assert filters == [[cnj_tjac], [cnj_tjsp]]
