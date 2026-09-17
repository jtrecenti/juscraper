"""Respostas offline do contrato de coleta, com transporte HTTP interceptado."""

import copy
import json
from datetime import date, datetime, timezone

import responses

from juscraper.courts.stf.download import BASE_URL, build_payload
from tests._helpers import load_sample


def sample_rows():
    return json.loads(load_sample("stf", "listar_decisoes/single_page.json"))["result"]["hits"]["hits"]


def make_rows(count, start="1988-01-01", days=2):
    from datetime import timedelta

    source = sample_rows()[0]["_source"]
    return [
        dict(
            source,
            id=f"doc-{i}",
            julgamento_data=(date.fromisoformat(start) + timedelta(days=i % days)).isoformat(),
            publicacao_data=(date.fromisoformat(start) + timedelta(days=i % days)).isoformat(),
        )
        for i in range(count)
    ]


class Source:
    def __init__(self, rows):
        self.rows = rows
        self.payloads = []
        self.before = None

    def install(self):
        responses.add_callback(responses.POST, BASE_URL, callback=self.respond, content_type="application/json")
        return self

    def respond(self, request):
        body = json.loads(request.body)
        self.payloads.append(body)
        if self.before:
            self.before(body)
        rows = self.select(body)
        response = json.loads(load_sample("stf", "collection/response.json"))
        result = response["result"]
        result["hits"]["total"]["value"] = len(rows)
        start = body["from"]
        end = start + body["size"]
        result["hits"]["hits"] = [{"_source": row} for row in rows[start:end]]
        if "collection_bounds" in body["aggs"]:
            field = body["aggs"]["collection_bounds"]["aggs"]["lower"]["min"]["field"]
            dates = sorted(row[field] for row in rows if row.get(field))
            agg = result["aggregations"]["collection_bounds"]
            agg["doc_count"] = len(rows)
            agg["missing"]["doc_count"] = len(rows) - len(dates)
            for name, value in (("lower", dates[0] if dates else None), ("upper", dates[-1] if dates else None)):
                if value is None:
                    agg[name] = {"value": None}
                else:
                    agg[name] = {
                        "value": datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000,
                        "value_as_string": value,
                    }
        else:
            result.pop("aggregations")
        return 200, {}, json.dumps(response)

    def select(self, body):
        rows = self.rows
        query = body["query"]["function_score"]["query"]["bool"]
        for clause in query["filter"]:
            if "range" in clause:
                field, interval = next(iter(clause["range"].items()))
                lower = datetime.strptime(interval["from"], "%d%m%Y").date().isoformat() if "from" in interval else None
                upper = datetime.strptime(interval["lte"], "%d%m%Y").date().isoformat() if "lte" in interval else None
                rows = [
                    row
                    for row in rows
                    if row.get(field)
                    and (lower is None or row[field] >= lower)
                    and (upper is None or row[field] <= upper)
                ]
        for clause in query.get("must_not", []):
            rows = [row for row in rows if not row.get(clause["exists"]["field"])]
        return rows


def add_sample(sample, **kwargs):
    response = json.loads(load_sample("stf", f"listar_decisoes/{sample}"))
    if kwargs.get("classe"):
        value = kwargs["classe"]
        kwargs["classe"] = sorted(set([value] if isinstance(value, str) else value))
    expected = build_payload(**kwargs)
    expected["aggs"] = {}
    expected["track_total_hits"] = True

    def match(request):
        actual = json.loads(request.body)
        wanted = copy.deepcopy(expected)
        wanted["query"]["function_score"]["functions"] = actual["query"]["function_score"]["functions"]
        return (actual == wanted, "payload de coleta diferente do esperado")

    def count_match(request):
        actual = json.loads(request.body)
        wanted = copy.deepcopy(expected)
        wanted["query"]["function_score"]["functions"] = actual["query"]["function_score"]["functions"]
        wanted["from"] = wanted["size"] = 0
        return (actual == wanted, "payload de contagem diferente do esperado")

    responses.add(responses.POST, BASE_URL, json=response, match=[match])
    if kwargs.get("pagina", 1) == 1:
        responses.add(responses.POST, BASE_URL, json=response, match=[count_match])
