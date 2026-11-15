"""Testes unitarios da extracao de contagem TJRR via util compartilhado (refs #87)."""
from __future__ import annotations

import pytest

from juscraper.courts.tjrr import download
from juscraper.courts.tjrr.download import (
    _datatables_with_pages,
    _download_page,
    _extract_datatable_id,
    _get_total_pages,
    _paginate,
)
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjrr", f"cjsg/{name}")


def test_get_total_pages_results_normal():
    html = _sample("step_02_search.html")
    assert _get_total_pages(html) == 1383


def test_get_total_pages_single_page_sample():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 65


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


def test_datatables_with_pages_reads_each_paginator():
    """Cada tabela de resultados tem paginador próprio (issue #319): 1383
    páginas de acórdãos e 330 de monocráticas no sample."""
    html = _sample("step_02_search.html")
    dtid = _extract_datatable_id(html)
    assert _datatables_with_pages(html) == [(dtid, 1383), (f"{dtid}2", 330)]


def test_datatables_with_pages_no_results_sample():
    html = _sample("no_results.html")
    dtid = _extract_datatable_id(html)
    assert _datatables_with_pages(html) == [(dtid, 1), (f"{dtid}2", 1)]


def test_datatables_with_pages_without_second_table():
    html = (
        '<div id="formPesquisa:j_idt1:dataTablePesquisa">'
        '<span class="ui-paginator-current">(1 of 7)</span></div>'
    )
    assert _datatables_with_pages(html) == [("formPesquisa:j_idt1:dataTablePesquisa", 7)]


def test_datatables_with_pages_without_datatable():
    """Página sem tabela de resultados não levanta: a página 1 continua
    utilizável, como antes da #319."""
    assert _datatables_with_pages("<html><body>nada</body></html>") == []


def _no_request(*args, **kwargs):
    """``request_fn`` que não deve ser chamado: ``_paginate`` está mockado."""
    raise AssertionError("request_fn não deveria ser chamado")


def _fake_paginate(calls: list):
    def fake(request_fn, html, page, datatable_id=None):
        calls.append((page, datatable_id))
        return f"<{datatable_id}:{page}>"
    return fake


def test_download_page_pages_both_tables_and_joins(mocker):
    calls: list = []
    mocker.patch.object(download, "_paginate", _fake_paginate(calls))
    sleep = mocker.patch("time.sleep")
    out = _download_page(_no_request, "", 2, [("a", 5), ("a2", 3)], 0.5)
    assert calls == [(2, "a"), (2, "a2")]
    assert out == "<a:2><a2:2>"
    assert sleep.call_count == 2


def test_download_page_skips_table_past_its_end(mocker):
    calls: list = []
    mocker.patch.object(download, "_paginate", _fake_paginate(calls))
    mocker.patch("time.sleep")
    _download_page(_no_request, "", 4, [("a", 5), ("a2", 3)], 0)
    assert calls == [(4, "a")]


def test_download_page_past_every_table_requests_acordaos(mocker):
    """Página explícita além do fim das duas tabelas: pede a de acórdãos,
    como antes da #319, e o backend decide o que devolver."""
    calls: list = []
    mocker.patch.object(download, "_paginate", _fake_paginate(calls))
    mocker.patch("time.sleep")
    _download_page(_no_request, "", 9, [("a", 5), ("a2", 3)], 0)
    assert calls == [(9, "a")]


_NO_DATATABLE_HTML = (
    '<form id="formPesquisa">'
    '<input type="hidden" name="javax.faces.ViewState" value="vs"/></form>'
)


def test_download_page_without_datatable_raises():
    """Sem tabela na página 1, pedir a página 2 continua levantando o erro
    de ``_extract_datatable_id``, em vez de devolver vazio em silêncio."""
    with pytest.raises(RuntimeError, match="datatable id"):
        _download_page(_no_request, _NO_DATATABLE_HTML, 2, [], 0)


def test_manager_paginas_none_runs_until_longest_table(mocker):
    """Com ``paginas=None``, o download vai até o fim da tabela mais longa,
    mesmo quando é a de monocráticas."""
    calls: list = []
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value="<p1>")
    mocker.patch.object(
        download, "_datatables_with_pages", return_value=[("a", 1), ("a2", 3)]
    )
    mocker.patch.object(download, "_paginate", _fake_paginate(calls))
    mocker.patch("time.sleep")
    out = download.cjsg_download_manager("x", None, request_fn=_no_request)
    assert out == ["<p1>", "<a2:2>", "<a2:3>"]
    assert calls == [(2, "a2"), (3, "a2")]
