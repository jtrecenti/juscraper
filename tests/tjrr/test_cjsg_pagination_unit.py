"""Testes unitarios da extracao de contagem TJRR via util compartilhado (refs #87)."""
from __future__ import annotations

import re

import pytest
from bs4 import BeautifulSoup

from juscraper.courts.tjrr import download
from juscraper.courts.tjrr.download import (
    _datatables_with_pages,
    _download_page,
    _extract_datatable_id,
    _get_total_pages,
    _paginate,
    _pagination_form,
)
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjrr", f"cjsg/{name}")


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_get_total_pages_results_normal():
    html = _sample("step_02_search.html")
    assert _get_total_pages(html) == 1383


def test_get_total_pages_single_page_sample():
    html = _sample("single_page.html")
    assert _get_total_pages(html) == 65


def test_get_total_pages_no_results_sample():
    html = _sample("no_results.html")
    assert _get_total_pages(html) == 1


def test_get_total_pages_sem_o_paginador_levanta():
    r"""HTML derivado do sample real ``single_page.html``, sem o paginador.

    Sem ele, o total não vira 1 página (o download parava na primeira) nem
    2009, da ementa que diz "(fevereiro de 2009)" e casa ``de\s+(\d+)\)``
    no HTML bruto.
    """
    html = re.sub(r'<span class="ui-paginator-current">[^<]*</span>', "", _sample("single_page.html"))
    assert "ui-paginator-current" not in html
    assert "(fevereiro de 2009)" in html
    with pytest.raises(ValueError, match="TJRR: a tabela de resultados não traz o paginador"):
        _get_total_pages(html)
    with pytest.raises(ValueError, match="TJRR"):
        _datatables_with_pages(html, _soup(html))


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

    form = _pagination_form(_soup(html))
    _paginate(fake_request_fn, form, page=2, datatable_id=dtid)

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
    # ViewState da página 1, que o backend aceita em todas as páginas.
    assert data["javax.faces.ViewState"] == form["javax.faces.ViewState"]
    # Header AJAX que o backend JSF usa para tratar como partial-response.
    assert headers["Faces-Request"] == "partial/ajax"
    assert headers["X-Requested-With"] == "XMLHttpRequest"


_MONOCRATICAS = "dataTablePesquisa2"


@pytest.mark.parametrize(
    ("sample", "n_acordaos", "n_monocraticas"),
    [("step_02_search.html", 1383, 330), ("no_results.html", 1, 1)],
)
def test_datatables_with_pages_reads_each_paginator(sample, n_acordaos, n_monocraticas):
    """Cada tabela de resultados tem paginador próprio (#319)."""
    html = _sample(sample)
    assert _datatables_with_pages(html, _soup(html)) == [
        (_extract_datatable_id(html), n_acordaos),
        (_extract_datatable_id(html, _MONOCRATICAS), n_monocraticas),
    ]


def test_datatables_with_pages_without_second_table():
    html = (
        '<div id="formPesquisa:j_idt1:dataTablePesquisa">'
        '<span class="ui-paginator-current">(1 of 7)</span></div>'
    )
    assert _datatables_with_pages(html, _soup(html)) == [("formPesquisa:j_idt1:dataTablePesquisa", 7)]


def test_datatables_with_pages_finds_second_table_in_other_container():
    """O id da tabela de monocráticas é procurado por conta própria: se o
    número JSF dela divergir do da de acórdãos, ela não some em silêncio."""
    html = (
        '<div id="formPesquisa:j_idt1:dataTablePesquisa">'
        '<span class="ui-paginator-current">(1 of 7)</span></div>'
        '<div id="formPesquisa:j_idt9:dataTablePesquisa2">'
        '<span class="ui-paginator-current">(1 of 4)</span></div>'
    )
    assert _datatables_with_pages(html, _soup(html)) == [
        ("formPesquisa:j_idt1:dataTablePesquisa", 7),
        ("formPesquisa:j_idt9:dataTablePesquisa2", 4),
    ]


def test_datatables_with_pages_without_datatable():
    """Página sem tabela de resultados não levanta: a página 1 continua
    utilizável, como antes da #319."""
    html = "<html><body>nada</body></html>"
    assert _datatables_with_pages(html, _soup(html)) == []


def _no_request(*args, **kwargs):
    """``request_fn`` que não deve ser chamado: ``_paginate`` está mockado."""
    raise AssertionError("request_fn não deveria ser chamado")


@pytest.fixture
def paginate_calls(mocker) -> list:
    """Troca ``_paginate`` e ``time.sleep`` por dublês; devolve as chamadas
    a ``_paginate`` como ``(page, datatable_id)``."""
    calls: list = []

    def fake(request_fn, form, page, datatable_id):
        calls.append((page, datatable_id))
        return f"<{datatable_id}:{page}>"

    mocker.patch.object(download, "_paginate", fake)
    mocker.patch("time.sleep")
    return calls


def test_download_page_pages_both_tables_and_joins(paginate_calls):
    out = _download_page(_no_request, {}, 2, [("a", 5), ("a2", 3)], 0.5)
    assert paginate_calls == [(2, "a"), (2, "a2")]
    assert out == "<a:2><a2:2>"


def test_download_page_skips_table_past_its_end(paginate_calls):
    _download_page(_no_request, {}, 4, [("a", 5), ("a2", 3)], 0)
    assert paginate_calls == [(4, "a")]


def test_download_page_past_every_table_requests_acordaos(paginate_calls):
    """Página explícita além do fim das duas tabelas: pede a de acórdãos,
    como antes da #319, e o backend decide o que devolver."""
    _download_page(_no_request, {}, 9, [("a", 5), ("a2", 3)], 0)
    assert paginate_calls == [(9, "a")]


def test_download_page_without_datatable_raises(paginate_calls):
    """Sem tabela na página 1, pedir a página 2 levanta, em vez de devolver
    vazio em silêncio."""
    with pytest.raises(RuntimeError, match="No results datatable"):
        _download_page(_no_request, {}, 2, [], 0)
    assert paginate_calls == []


@pytest.mark.parametrize(
    ("tables", "esperado", "chamadas"),
    [
        # Vai até o fim da tabela mais longa, mesmo quando é a de monocráticas.
        ([("a", 1), ("a2", 3)], ["<p1>", "<a2:2>", "<a2:3>"], [(2, "a2"), (3, "a2")]),
        # Paginador que lê 0 não apaga a página 1.
        ([("a", 0), ("a2", 0)], ["<p1>"], []),
    ],
)
def test_manager_paginas_none(mocker, paginate_calls, tables, esperado, chamadas):
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value="<p1>")
    mocker.patch.object(download, "_datatables_with_pages", return_value=tables)
    mocker.patch.object(download, "_pagination_form", return_value={})
    out = download.cjsg_download_manager("x", None, request_fn=_no_request)
    assert out == esperado
    assert paginate_calls == chamadas


def test_manager_paginas_1_nao_conta_paginas(mocker, paginate_calls):
    """Com ``paginas=1``, nenhuma contagem nem paginação é feita."""
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value="<p1>")
    contagem = mocker.patch.object(download, "_datatables_with_pages")
    form = mocker.patch.object(download, "_pagination_form")
    parse = mocker.spy(download, "BeautifulSoup")
    assert download.cjsg_download_manager("x", [1], request_fn=_no_request) == ["<p1>"]
    parse.assert_not_called()
    contagem.assert_not_called()
    form.assert_not_called()
    assert paginate_calls == []


def test_manager_le_o_form_da_pagina_1_uma_vez(mocker):
    """O HTML da página 1 é parseado uma vez, não a cada requisição de
    paginação: as quatro requisições (páginas 2 e 3 das duas tabelas)
    recebem o mesmo form."""
    html = _sample("step_02_search.html")
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value=html)
    mocker.patch("time.sleep")
    form = mocker.spy(download, "_pagination_form")
    recebidos: list = []

    def fake(request_fn, form, page, datatable_id):
        recebidos.append(form)
        return ""

    mocker.patch.object(download, "_paginate", fake)
    download.cjsg_download_manager("x", range(1, 4), request_fn=_no_request)
    assert form.call_count == 1
    assert len(recebidos) == 4
    assert all(r is form.spy_return for r in recebidos)
    assert recebidos[0]["formPesquisa:consultaAtual"] == "dano moral"


@pytest.mark.parametrize("paginas", [None, range(1, 4)])
def test_manager_parseia_o_html_da_pagina_1_uma_vez(mocker, paginas):
    """A contagem das tabelas e o form da paginação saem do mesmo parse do
    HTML inteiro da página 1, sem um ``BeautifulSoup`` para cada. A contagem
    (mockada aqui) ainda parseia o ``div`` de cada tabela no helper
    compartilhado ``extract_count_with_cascade``."""
    html = _sample("step_02_search.html")
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value=html)
    mocker.patch.object(download, "_get_total_pages", return_value=3)
    mocker.patch("time.sleep")
    mocker.patch.object(download, "_paginate", return_value="")
    parse = mocker.spy(download, "BeautifulSoup")
    form = mocker.spy(download, "_pagination_form")
    out = download.cjsg_download_manager("x", paginas, request_fn=_no_request)
    assert len(out) == 3
    assert parse.call_count == 1
    assert form.call_count == 1


def test_manager_sem_tabela_levanta_erro_da_tabela(mocker):
    """Página 1 sem tabela (nem ViewState): o erro diz que falta a tabela de
    resultados, não o ViewState."""
    mocker.patch.object(download, "_get_form_fields", return_value={})
    mocker.patch.object(download, "_search", return_value="<html><body>erro</body></html>")
    with pytest.raises(RuntimeError, match="No results datatable"):
        download.cjsg_download_manager("x", [1, 2], request_fn=_no_request)


def test_pagination_form_sem_viewstate_levanta():
    with pytest.raises(RuntimeError, match="ViewState"):
        _pagination_form(_soup("<html><body>sem form</body></html>"))
