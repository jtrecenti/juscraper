"""Testes unitarios da extracao de contagem TJRR via util compartilhado (refs #87)."""
from __future__ import annotations

import pytest

from juscraper.courts.tjrr.download import _extract_datatable_id, _get_total_pages, _paginate
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjrr", f"cjsg/{name}")


def test_get_total_pages_results_normal():
    html = _sample("step_02_search.html")
    assert _get_total_pages(html) == 1250


def test_get_total_pages_single_page_sample():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 59


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


def test_extract_datatable_id_falls_back_when_no_id_attribute():
    """Segundo nivel da cascata: o id aparece "solto" (ex.: em JS), sem o
    atributo ``id="..."``. O primeiro seletor (ancorado em ``id="``) nao casa e
    a busca cai para o seletor sem ancora, em vez de levantar."""
    html = (
        '<script>PrimeFaces.cw("DataTable","w",'
        '{id:"formPesquisa:j_idt300:dataTablePesquisa"});</script>'
    )
    assert _extract_datatable_id(html) == "formPesquisa:j_idt300:dataTablePesquisa"


def test_extract_datatable_id_falls_back_for_non_jidt_segment():
    r"""Terceiro nivel da cascata: o segmento do meio nao segue ``j_idt\d+``
    (ex.: id nomeado ``resultTable``). Os dois primeiros seletores (presos a
    ``j_idt\d+``) nao casam e o seletor generico ``[\w-]+`` resolve."""
    html = '<div id="formPesquisa:resultTable:dataTablePesquisa"></div>'
    assert _extract_datatable_id(html) == "formPesquisa:resultTable:dataTablePesquisa"


def test_extract_datatable_id_raises_when_absent():
    with pytest.raises(RuntimeError, match="datatable id"):
        _extract_datatable_id("<html><body>no datatable here</body></html>")


class _FakeResp:
    def __init__(self, text: str):
        self.text = text
        self.encoding = "utf-8"


def test_paginate_payload_replicates_browser():
    """Camada 2 da issue #287: o POST AJAX de paginação precisa ecoar o
    contexto completo do form de resultados (``consultaAtual``), disparar o
    evento de comportamento ``page`` do PrimeFaces, mandar as flags de
    feature do datatable e o offset ``_first`` absoluto — e enviar o header
    ``Faces-Request: partial/ajax``. O payload mínimo, sem essas peças, era
    silenciosamente ignorado pelo backend (devolvia sempre a página 1).
    Rede de segurança offline análoga aos testes de ``_extract_datatable_id``.
    """
    html = _sample("step_02_search.html")
    dtid = _extract_datatable_id(html)
    captured: dict = {}

    def fake_request_fn(method, url, **kwargs):
        captured["method"] = method
        captured["data"] = kwargs.get("data")
        captured["headers"] = kwargs.get("headers")
        return _FakeResp("<?xml version='1.0'?><partial-response></partial-response>")

    _paginate(fake_request_fn, html, page=2)

    data = captured["data"]
    headers = captured["headers"]
    # Contexto completo do form ecoado — o termo de busca é o canário.
    assert data["formPesquisa:consultaAtual"] == "dano moral"
    # Evento "page" de comportamento do PrimeFaces.
    assert data["javax.faces.behavior.event"] == "page"
    assert data["javax.faces.partial.event"] == "page"
    # Offset absoluto da página 2 (rows=10 -> first=10).
    assert data[f"{dtid}_first"] == "10"
    # Flags de feature do datatable.
    assert data[f"{dtid}_skipChildren"] == "true"
    assert data[f"{dtid}_encodeFeature"] == "true"
    # Header AJAX que o backend JSF usa para tratar como partial-response.
    assert headers["Faces-Request"] == "partial/ajax"
    assert headers["X-Requested-With"] == "XMLHttpRequest"
