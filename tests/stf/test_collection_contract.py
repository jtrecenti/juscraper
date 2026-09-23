"""Integridade e recuperação da coleta STF com fonte HTTP offline controlada."""

import json

import pandas as pd
import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.courts.stf._checkpoint import Checkpoint
from juscraper.courts.stf._collection import bounds_payload, exact_total
from juscraper.courts.stf.download import build_payload
from juscraper.courts.stf.schemas import InputListarDecisoesSTF
from tests._helpers import load_sample
from tests.stf._collection_helpers import Source, make_rows


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="secret-test-token", sleep_time=0, max_retries=0)


def manifest(directory):
    return json.loads((directory / "manifest.json").read_text())


def write_manifest(directory, value):
    (directory / "manifest.json").write_text(json.dumps(value))


def data_payloads(source):
    return [body for body in source.payloads if body["size"]]


@responses.activate
def test_resume_matches_uninterrupted_and_restarts_window(stf, tmp_path):
    source = Source(make_rows(6)).install()
    expected = stf.listar_decisoes(tamanho_pagina=2)
    source.payloads.clear()

    def interrupt(body):
        if body["from"] == 2:
            raise RuntimeError("interrupt")

    source.before = interrupt
    with pytest.raises(RuntimeError, match="interrupt"):
        stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path)
    original = manifest(tmp_path)
    first = original["root"]["attempts"][0]["pages"][0]
    assert (tmp_path / first["file"]).is_file()
    assert original["root"]["completed_at"] is None

    source.before = None
    source.payloads.clear()
    actual = stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path, resume=True)
    pd.testing.assert_frame_equal(expected, actual)
    assert data_payloads(source)[0]["from"] == 0
    finished = manifest(tmp_path)
    assert len(finished["root"]["attempts"]) == 2
    assert finished["reference_time"] == original["reference_time"]
    assert (tmp_path / first["file"]).is_file()
    assert "secret-test-token" not in "".join(path.read_text() for path in tmp_path.iterdir())
    origins = {
        body["query"]["function_score"]["functions"][0]["exp"]["julgamento_data"]["origin"] for body in source.payloads
    }
    assert origins == {original["reference_time"]}
    source.payloads.clear()
    pd.testing.assert_frame_equal(actual, stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path, resume=True))
    assert not source.payloads


@responses.activate
def test_crash_between_page_and_manifest_preserves_orphan(stf, tmp_path, monkeypatch):
    source = Source(make_rows(3)).install()
    save = Checkpoint.save

    def crash(store):
        if store.manifest.root.attempts and store.manifest.root.attempts[-1].pages:
            raise RuntimeError("after page")
        save(store)

    with monkeypatch.context() as patch:
        patch.setattr(Checkpoint, "save", crash)
        with pytest.raises(RuntimeError, match="after page"):
            stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path)
    files = set(tmp_path.glob("*.json")) - {tmp_path / "manifest.json"}
    assert len(files) == 1
    assert not manifest(tmp_path)["root"]["attempts"][0]["pages"]
    source.payloads.clear()
    df = stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path, resume=True)
    assert len(df) == 3
    assert data_payloads(source)[0]["from"] == 0
    assert all(path.exists() for path in files)


@responses.activate
def test_resume_does_not_union_abandoned_attempt(stf, tmp_path):
    source = Source(make_rows(4)).install()
    source.before = lambda body: (_ for _ in ()).throw(RuntimeError("stop")) if body["from"] == 2 else None
    with pytest.raises(RuntimeError):
        stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path)
    old_id = source.rows[0]["id"]
    source.rows[0] = dict(source.rows[0], id="replacement")
    source.before = None
    df = stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path, resume=True)
    assert set(df.id) == {row["id"] for row in source.rows}
    assert old_id not in set(df.id)
    assert any(old_id in path.read_text() for path in tmp_path.glob("*.json") if path.name != "manifest.json")


@pytest.mark.parametrize(
    "change",
    [
        {"pesquisa": "different"},
        {"base": "acordaos"},
        {"tamanho_pagina": 1},
        {"paginas": [1]},
        {"classe": "Rcl"},
        {"inteiro_teor": True},
        {"data_julgamento_fim": "2020-01-01"},
    ],
)
@responses.activate
def test_incompatible_resume_before_http(stf, tmp_path, change):
    source = Source(make_rows(2)).install()
    stf.listar_decisoes(checkpoint_dir=tmp_path)
    source.payloads.clear()
    with pytest.raises(ValueError, match="incompatível"):
        stf.listar_decisoes(checkpoint_dir=tmp_path, resume=True, **change)
    assert not source.payloads


@responses.activate
def test_identity_preserves_query_and_normalizes_filters(stf, tmp_path):
    source = Source(make_rows(2)).install()
    stf.listar_decisoes("x ou y$", classe="Rcl", data_julgamento_fim="31/12/2020", checkpoint_dir=tmp_path)
    source.payloads.clear()
    stf.listar_decisoes(
        "x OR y*", classe=["Rcl", "Rcl"], data_julgamento_fim="2020-12-31", checkpoint_dir=tmp_path, resume=True
    )
    assert not source.payloads
    with pytest.raises(ValueError, match="incompatível"):
        stf.listar_decisoes(
            "x  OR y*", classe="Rcl", data_julgamento_fim="2020-12-31", checkpoint_dir=tmp_path, resume=True
        )


@responses.activate
def test_occupied_and_missing_checkpoint_fail_before_http(stf, tmp_path):
    source = Source(make_rows(1)).install()
    with pytest.raises(ValueError, match="exige"):
        stf.listar_decisoes(resume=True)
    with pytest.raises(ValueError, match="inexistente"):
        stf.listar_decisoes(checkpoint_dir=tmp_path / "absent", resume=True)
    (tmp_path / "user-file").write_text("preserve")
    with pytest.raises(ValueError, match="ocupado"):
        stf.listar_decisoes(checkpoint_dir=tmp_path)
    assert (tmp_path / "user-file").read_text() == "preserve"
    assert not source.payloads


@pytest.mark.parametrize(
    "corruption", ["json", "version", "missing_root", "page", "checksum", "path", "total", "pages", "unknown"]
)
@responses.activate
def test_corrupt_checkpoint_rejected_before_http(stf, tmp_path, corruption):
    source = Source(make_rows(3)).install()
    stf.listar_decisoes(checkpoint_dir=tmp_path, tamanho_pagina=2)
    state = manifest(tmp_path)
    attempt = state["root"]["attempts"][-1]
    page = attempt["pages"][0]
    if corruption == "json":
        (tmp_path / "manifest.json").write_text("{")
    elif corruption == "page":
        (tmp_path / page["file"]).rename(tmp_path / "missing-page")
    elif corruption == "checksum":
        (tmp_path / page["file"]).write_text("[]")
    else:
        if corruption == "version":
            state["version"] = 99
        elif corruption == "missing_root":
            state.pop("root")
        elif corruption == "path":
            page["file"] = "../outside.json"
        elif corruption == "total":
            attempt["total_after"] = 99
        elif corruption == "pages":
            attempt["pages"].pop()
        elif corruption == "unknown":
            state["unexpected"] = True
        write_manifest(tmp_path, state)
    source.payloads.clear()
    with pytest.raises(ValueError, match="corrompido"):
        stf.listar_decisoes(checkpoint_dir=tmp_path, tamanho_pagina=2, resume=True)
    assert not source.payloads


@responses.activate
def test_cross_window_duplicate_never_marks_root_complete(stf, tmp_path, monkeypatch):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 4)
    monkeypatch.setattr("juscraper.courts.stf.download.MAX_REGISTROS", 4)
    rows = make_rows(6)
    rows[1]["id"] = rows[0]["id"]
    source = Source(rows).install()
    with pytest.raises(ValueError, match="duplicados entre janelas"):
        stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path)
    state = manifest(tmp_path)
    assert state["root"]["completed_at"] is None
    assert state["root"]["children"][0]["completed_at"] is None
    source.payloads.clear()
    with pytest.raises(ValueError, match="duplicados entre janelas"):
        stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path, resume=True)
    assert not source.payloads


@responses.activate
def test_without_checkpoint_does_not_write(stf, monkeypatch):
    Source(make_rows(3)).install()
    monkeypatch.setattr(Checkpoint, "_write", lambda *args: pytest.fail("unexpected write"))
    assert len(stf.listar_decisoes()) == 3


@pytest.mark.parametrize("total", [0, 10000, 10001])
@responses.activate
def test_cap_exact_over_and_non_divisor(stf, total):
    source = Source(make_rows(total)).install()
    df = stf.listar_decisoes(tamanho_pagina=249)
    assert len(df) == total
    assert all(body["from"] + body["size"] <= 10000 for body in source.payloads)
    if total == 10000:
        assert data_payloads(source)[-1]["size"] == 40
        assert not any("collection_bounds" in body["aggs"] for body in source.payloads)
    if total == 10001:
        assert any("collection_bounds" in body["aggs"] for body in source.payloads)


@responses.activate
def test_closed_disjoint_boundaries_and_empty_middle(stf, monkeypatch):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    rows = make_rows(4, start="2020-01-01", days=2)
    for index, row in enumerate(rows):
        row["julgamento_data"] = "2020-01-01" if index < 2 else "2020-01-08"
    source = Source(rows).install()
    df = stf.listar_decisoes(data_julgamento_inicio="2020-01-01", data_julgamento_fim="2020-01-08")
    assert set(df.id) == {row["id"] for row in rows}
    assert not any("collection_bounds" in body["aggs"] for body in source.payloads)
    assert all(body["post_filter"]["bool"]["must"][0] == {"term": {"base": "decisoes"}} for body in source.payloads)


@pytest.mark.parametrize("axis", ["julgamento", "publicacao"])
@responses.activate
def test_open_bounds_before_1990_and_missing(stf, monkeypatch, axis):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    rows = make_rows(5, start="1988-01-01", days=3)
    if axis == "julgamento":
        rows[-1]["julgamento_data"] = None
    source = Source(rows).install()
    filters = {"data_publicacao_fim": "1991-01-01"} if axis == "publicacao" else {}
    df = stf.listar_decisoes(classe="Rcl", **filters)
    assert set(df.id) == {row["id"] for row in rows}
    discovery = next(body for body in source.payloads if "collection_bounds" in body["aggs"])
    agg = discovery["aggs"]["collection_bounds"]
    assert agg["filter"] == discovery["post_filter"]
    assert agg["aggs"]["lower"]["min"]["field"] == f"{axis}_data"
    assert "01011990" not in json.dumps(source.payloads)
    assert any(body["query"]["function_score"]["query"]["bool"].get("must_not") for body in source.payloads)


@responses.activate
def test_open_lower_bound_is_not_filled(stf):
    source = Source(make_rows(1)).install()
    stf.listar_decisoes(data_julgamento_inicio="1980-01-01")
    ranges = source.payloads[0]["query"]["function_score"]["query"]["bool"]["filter"]
    assert ranges[1] == {"range": {"julgamento_data": {"format": "ddMMyyyy", "from": "01011980"}}}


@pytest.mark.parametrize("missing", [False, True])
@responses.activate
def test_saturated_day_and_missing_raise(stf, monkeypatch, missing):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    rows = make_rows(3, days=1)
    if missing:
        for row in rows:
            row["julgamento_data"] = None
    Source(rows).install()
    with pytest.raises(ValueError, match=r"sem data|saturado"):
        stf.listar_decisoes()


@responses.activate
def test_explicit_page_keeps_offset_without_slicing(stf):
    source = Source(make_rows(10001)).install()
    df = stf.listar_decisoes(paginas=[2], tamanho_pagina=3)
    assert list(df.id) == ["doc-3", "doc-4", "doc-5"]
    assert data_payloads(source)[0]["from"] == 3
    assert not any("collection_bounds" in body["aggs"] for body in source.payloads)


@pytest.mark.parametrize("kind", ["missing", "empty", "wrong_base", "duplicated_page", "duplicated_pages"])
@responses.activate
def test_document_identity_is_required_and_unique(stf, kind):
    rows = make_rows(4)
    if kind == "missing":
        rows[0].pop("id")
    elif kind == "empty":
        rows[0]["id"] = ""
    elif kind == "wrong_base":
        rows[0]["base"] = "acordaos"
    elif kind == "duplicated_page":
        rows[1]["id"] = rows[0]["id"]
    else:
        rows[2]["id"] = rows[0]["id"]
    Source(rows).install()
    with pytest.raises(ValueError, match=r"identidade|duplicad"):
        stf.listar_decisoes(tamanho_pagina=2)


@pytest.mark.parametrize(
    "total",
    [{"value": 2, "relation": "gte"}, {"value": True, "relation": "eq"}, {"value": -1, "relation": "eq"}, 2, {}],
)
def test_inexact_total_rejected(total):
    response = json.loads(load_sample("stf", "collection/response.json"))
    response["result"]["hits"]["total"] = total
    with pytest.raises(ValueError):
        exact_total(response)


@pytest.mark.parametrize("when", ["page", "after"])
@responses.activate
def test_count_change_during_window_fails(stf, when):
    source = Source(make_rows(4)).install()

    def change(body):
        if (when == "page" and body["from"] == 2) or (when == "after" and len(source.payloads) == 4):
            source.rows.pop()

    source.before = change
    with pytest.raises(ValueError, match="Contagem STF mudou"):
        stf.listar_decisoes(tamanho_pagina=2)


@responses.activate
def test_equal_counts_with_mutation_do_not_claim_snapshot(stf, tmp_path):
    source = Source(make_rows(4)).install()

    def mutate(body):
        if body["from"] == 2:
            source.rows[0] = dict(source.rows[0], id="new-first")

    source.before = mutate
    df = stf.listar_decisoes(tamanho_pagina=2, checkpoint_dir=tmp_path)
    assert len(df) == 4
    assert set(df.id) != {row["id"] for row in source.rows}
    assert "snapshot" not in json.dumps(manifest(tmp_path)).lower()
    assert "sem garantir snapshot" in stf.listar_decisoes.__doc__


@responses.activate
def test_completed_windows_are_not_refetched_on_resume(stf, tmp_path, monkeypatch):
    monkeypatch.setattr("juscraper.courts.stf._collection.MAX_REGISTROS", 2)
    source = Source(make_rows(4)).install()

    def interrupt(body):
        query = json.dumps(body["query"])
        if body["size"] and "02011988" in query:
            raise RuntimeError("stop")

    source.before = interrupt
    with pytest.raises(RuntimeError):
        stf.listar_decisoes(checkpoint_dir=tmp_path)
    first = manifest(tmp_path)["root"]["children"][0]["children"][0]
    assert first["completed_at"]
    source.before = None
    source.payloads.clear()
    assert len(stf.listar_decisoes(checkpoint_dir=tmp_path, resume=True)) == 4
    assert all("01011988" not in json.dumps(body["query"]) for body in data_payloads(source))
    assert manifest(tmp_path)["root"]["children"][0]["children"][0]["completed_at"] == first["completed_at"]


def test_checkpoint_schema_is_forbid_and_accepts_path(tmp_path):
    inp = InputListarDecisoesSTF(pesquisa="*", checkpoint_dir=tmp_path, resume=True)
    assert inp.checkpoint_dir == tmp_path
    with pytest.raises(ValidationError):
        InputListarDecisoesSTF(pesquisa="*", checkpoint=tmp_path)


def test_bounds_payload_applies_post_filter_and_exact_format():
    payload = bounds_payload(build_payload(classe="Rcl", tamanho_pagina=0), "julgamento_data")
    agg = payload["aggs"]["collection_bounds"]
    assert agg["filter"] == payload["post_filter"]
    assert agg["aggs"]["lower"] == {"min": {"field": "julgamento_data", "format": "yyyy-MM-dd"}}


class ReplicaSource(Source):
    """Réplicas que discordam do score: a ordem por relevância muda a cada requisição."""

    def __init__(self, rows):
        super().__init__(rows)
        self.score_requests = 0

    def select(self, body):
        rows = super().select(body)
        if body["sort"] == [{"id": "asc"}]:
            return sorted(rows, key=lambda row: row["id"])
        self.score_requests += 1
        return rows if self.score_requests % 2 else rows[::-1]


@responses.activate
def test_full_collection_orders_by_id_despite_unstable_scores(stf):
    source = ReplicaSource(make_rows(7)).install()
    df = stf.listar_decisoes(tamanho_pagina=2)
    assert sorted(df.id) == sorted(f"doc-{i}" for i in range(7))
    assert all(body["sort"] == [{"id": "asc"}] for body in data_payloads(source))


@responses.activate
def test_explicit_pages_keep_portal_order(stf):
    source = Source(make_rows(5)).install()
    stf.listar_decisoes(paginas=[1], tamanho_pagina=2)
    assert data_payloads(source)[0]["sort"] == [{"_score": "desc"}, {"id": "asc"}]
