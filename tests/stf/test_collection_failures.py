"""Falhas de contrato do endpoint e da persistência local, sem rede real."""

import copy
import hashlib
import json
from pathlib import Path

import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.stf._checkpoint import Checkpoint
from juscraper.courts.stf.download import BASE_URL
from tests.stf._collection_helpers import Source, make_rows


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="test", sleep_time=0, max_retries=0)


def intercept(source, transform):
    def callback(request):
        status, headers, text = source.respond(request)
        response = json.loads(text)
        transform(json.loads(request.body), response["result"])
        return status, headers, json.dumps(response)

    responses.add_callback(responses.POST, BASE_URL, callback=callback, content_type="application/json")


@pytest.mark.parametrize("corruption", ["absent", "count", "negative", "inverted", "invalid_date", "total"])
@responses.activate
def test_bad_bounds_response_fails_explicitly(stf, monkeypatch, corruption):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    source = Source(make_rows(4))

    def corrupt(body, result):
        if "collection_bounds" not in body["aggs"]:
            return
        bounds = result["aggregations"]["collection_bounds"]
        if corruption == "absent":
            result.pop("aggregations")
        elif corruption == "count":
            bounds["doc_count"] = 1
        elif corruption == "negative":
            bounds["missing"]["doc_count"] = -1
        elif corruption == "inverted":
            bounds["lower"], bounds["upper"] = bounds["upper"], bounds["lower"]
        elif corruption == "invalid_date":
            bounds["lower"] = {"value": None}
        else:
            result["hits"]["total"]["value"] += 1

    intercept(source, corrupt)
    with pytest.raises(ValueError):
        stf.listar_decisoes()


@responses.activate
def test_epoch_bounds_without_formatted_value(stf, monkeypatch):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    source = Source(make_rows(4))

    def remove_format(body, result):
        if "collection_bounds" in body["aggs"]:
            bounds = result["aggregations"]["collection_bounds"]
            bounds["lower"].pop("value_as_string")
            bounds["upper"].pop("value_as_string")

    intercept(source, remove_format)
    assert len(stf.listar_decisoes()) == 4


@pytest.mark.parametrize("failure", ["inexact", "short_page"])
@responses.activate
def test_http_inexact_count_or_short_page_never_returns_partial(stf, failure):
    source = Source(make_rows(4))

    def change(body, result):
        if failure == "inexact":
            result["hits"]["total"]["relation"] = "gte"
        elif body["size"]:
            result["hits"]["hits"].pop()

    intercept(source, change)
    with pytest.raises(ValueError):
        stf.listar_decisoes()


@pytest.mark.parametrize("failure", ["parent_count", "missing_grew", "duplicate_across_windows"])
@responses.activate
def test_mutations_across_partitions_fail(stf, monkeypatch, failure):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    source = Source(make_rows(4)).install()
    if failure == "duplicate_across_windows":
        source.rows[1]["id"] = source.rows[0]["id"]
    else:

        def change(body):
            query = body["query"]["function_score"]["query"]["bool"]
            if failure == "missing_grew" and query.get("must_not"):
                source.rows.extend(
                    dict(row, julgamento_data=None, id=f"missing-{i}") for i, row in enumerate(make_rows(3))
                )
            if failure == "parent_count" and len(source.payloads) > 2 and len(query["filter"]) == 1:
                source.rows.pop()

        source.before = change
    with pytest.raises(ValueError, match=r"Contagem|sem data|duplicados"):
        stf.listar_decisoes()


@responses.activate
def test_checkpoint_lock_rejects_parallel_resume_before_http(stf, tmp_path):
    source = Source(make_rows(2)).install()
    stf.listar_decisoes(checkpoint_dir=tmp_path)
    state = json.loads((tmp_path / "manifest.json").read_text())
    store = Checkpoint(tmp_path, True, state["identity"])
    source.payloads.clear()
    try:
        with pytest.raises(ValueError, match="em uso"):
            stf.listar_decisoes(checkpoint_dir=tmp_path, resume=True)
        assert not source.payloads
    finally:
        store.close()


@responses.activate
def test_manifest_replace_failure_keeps_previous_progress(stf, tmp_path, monkeypatch):
    Source(make_rows(3)).install()
    replace = Path.replace

    def fail_after_page(path, target):
        state = json.loads(path.read_text())
        if state["root"]["attempts"] and state["root"]["attempts"][-1]["pages"]:
            raise OSError("replace failed")
        return replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail_after_page)
        with pytest.raises(OSError, match="replace failed"):
            stf.listar_decisoes(checkpoint_dir=tmp_path)
    state = json.loads((tmp_path / "manifest.json").read_text())
    assert not state["root"]["attempts"][-1]["pages"]
    assert list(tmp_path.glob("manifest-*.tmp"))
    assert len(stf.listar_decisoes(checkpoint_dir=tmp_path, resume=True)) == 3


@pytest.mark.parametrize("corruption", ["duplicate", "content", "symlink", "window_total", "missing_attempt"])
@responses.activate
def test_checkpoint_structural_corruption_before_http(stf, tmp_path, corruption):
    source = Source(make_rows(4)).install()
    stf.listar_decisoes(checkpoint_dir=tmp_path, tamanho_pagina=2)
    state = json.loads((tmp_path / "manifest.json").read_text())
    attempt = state["root"]["attempts"][-1]
    page = attempt["pages"][0]
    if corruption == "duplicate":
        attempt["pages"].append(copy.deepcopy(page))
    elif corruption == "content":
        data = b"{}"
        (tmp_path / page["file"]).write_bytes(data)
        page["sha256"] = hashlib.sha256(data).hexdigest()
    elif corruption == "symlink":
        original = tmp_path / page["file"]
        target = tmp_path / "saved-page"
        original.rename(target)
        original.symlink_to(target)
    elif corruption == "window_total":
        state["root"]["total_before"] = state["root"]["total_after"] = 99
    else:
        state["root"]["attempts"] = []
    (tmp_path / "manifest.json").write_text(json.dumps(state))
    source.payloads.clear()
    with pytest.raises(ValueError, match="corrompido"):
        stf.listar_decisoes(checkpoint_dir=tmp_path, tamanho_pagina=2, resume=True)
    assert not source.payloads


@pytest.mark.parametrize("paginas", [10**9, range(1, 10**9), range(1, 10**9, 3)])
@pytest.mark.parametrize("tamanho", [1, 249, 250])
@responses.activate
def test_paginacao_excessiva_falha_antes_de_materializar(stf, mocker, tmp_path, paginas, tamanho):
    materializar = mocker.patch(
        "juscraper.courts.stf._collection.list",
        create=True,
        side_effect=AssertionError("Seleção inválida não deve ser materializada."),
    )
    diretorio = tmp_path / "checkpoint"
    with pytest.raises(ValueError, match="10000 primeiros registros"):
        stf.listar_decisoes(paginas=paginas, tamanho_pagina=tamanho, checkpoint_dir=diretorio)
    materializar.assert_not_called()
    assert not responses.calls
    assert not diretorio.exists()


@pytest.mark.parametrize(
    "paginas,tamanho,inicio,fim",
    [(range(40, 41), 250, 9750, 10000), (range(41, 42), 249, 9960, 10000), (range(2, 10**9, 10**9), 2, 2, 4)],
)
@responses.activate
def test_range_valido_preserva_ultima_pagina_e_passo(stf, paginas, tamanho, inicio, fim):
    fonte = Source(make_rows(10001)).install()

    resultado = stf.listar_decisoes(paginas=paginas, tamanho_pagina=tamanho)

    assert resultado.id.tolist() == [registro["id"] for registro in fonte.rows[inicio:fim]]
    corpos = [corpo for corpo in fonte.payloads if corpo["size"]]
    assert len(corpos) == 1
    assert (corpos[0]["from"], corpos[0]["size"]) == (inicio, fim - inicio)


@pytest.mark.parametrize("kwargs", [{"paginas": [1, 1]}, {"tamanho_pagina": 251}, {"resume": []}])
@responses.activate
def test_invalid_input_fails_before_request(stf, kwargs):
    with pytest.raises((ValueError, ValidationError)):
        stf.listar_decisoes(**kwargs)
    assert not responses.calls
