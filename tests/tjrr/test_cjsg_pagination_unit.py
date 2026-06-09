"""Testes unitarios da extracao de contagem TJRR via util compartilhado (refs #87)."""
from __future__ import annotations

import pytest

from juscraper.courts.tjrr.download import _extract_datatable_id, _get_total_pages
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjrr", f"cjsg/{name}")


def test_get_total_pages_results_normal():
    html = _sample("step_02_search.html")
    assert _get_total_pages(html) == 1210


def test_get_total_pages_single_page_sample():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 58


def test_get_total_pages_no_results_sample():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_falls_back_to_one_without_paginator():
    assert _get_total_pages("<html><body>nada de paginator</body></html>") == 1


def test_get_total_pages_resilient_to_class_change():
    html = (
        '<div class="paginator"><span class="paginator-status">'
        "(1 of 99)</span></div>"
    )
    assert _get_total_pages(html) == 99


def test_extract_datatable_id_from_results_sample():
    """The pagination id is read from the rendered page, never hardcoded."""
    dtid = _extract_datatable_id(_sample("step_02_search.html"))
    assert dtid.startswith("formPesquisa:j_idt")
    assert dtid.endswith(":dataTablePesquisa")


def test_extract_datatable_id_follows_jsf_drift():
    """A different auto-generated id (the j_idt159 -> j_idt158 drift that broke
    pagination in prod) is picked up verbatim instead of falling back to a stale
    constant."""
    html = '<div id="formPesquisa:j_idt777:dataTablePesquisa" class="ui-datatable"></div>'
    assert _extract_datatable_id(html) == "formPesquisa:j_idt777:dataTablePesquisa"


def test_extract_datatable_id_pins_base_table_not_second_or_tbody():
    """Must pin the base datatable id, not ``dataTablePesquisa2`` (the second,
    distinct results table) nor the ``_data`` tbody."""
    html = (
        '<div id="formPesquisa:j_idt158:dataTablePesquisa2"></div>'
        '<tbody id="formPesquisa:j_idt158:dataTablePesquisa_data"></tbody>'
        '<div id="formPesquisa:j_idt158:dataTablePesquisa"></div>'
    )
    assert _extract_datatable_id(html) == "formPesquisa:j_idt158:dataTablePesquisa"


def test_extract_datatable_id_raises_when_absent():
    with pytest.raises(RuntimeError, match="datatable id"):
        _extract_datatable_id("<html><body>no datatable here</body></html>")
