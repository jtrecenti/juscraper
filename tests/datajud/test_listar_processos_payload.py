"""Garante que o payload Elasticsearch enviado por listar_processos sempre
carrega `numeroProcesso` apenas com dígitos, em todos os caminhos de entrada
(refs #60).
"""
import pytest

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client

CNJ_FORMATADO_TJAC = "0003325-88.2014.8.01.0001"
CNJ_LIMPO_TJAC = "00033258820148010001"


@pytest.fixture
def captured_payloads(monkeypatch):
    payloads = []

    def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
        payloads.append(query_payload)
        return {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}

    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
    return payloads


def _numero_processo_no_payload(payload):
    must = payload["query"]["bool"]["must"]
    terms = next(c for c in must if "terms" in c and "numeroProcesso" in c["terms"])
    return terms["terms"]["numeroProcesso"]


class TestNumeroProcessoLimpoNoPayload:
    def test_numero_processo_string_formatada(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.listar_processos(numero_processo=CNJ_FORMATADO_TJAC)

        assert captured_payloads, "call_datajud_api não foi chamado"
        nproc = _numero_processo_no_payload(captured_payloads[0])
        assert nproc == [CNJ_LIMPO_TJAC]

    def test_numero_processo_lista_formatada(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.listar_processos(numero_processo=[CNJ_FORMATADO_TJAC])

        nproc = _numero_processo_no_payload(captured_payloads[0])
        assert nproc == [CNJ_LIMPO_TJAC]

    def test_tribunal_mais_numero_processo_formatado(self, captured_payloads):
        # Caso A do problema 1: o caminho `tribunal=` + `numero_processo=`
        # antes não passava por clean_cnj.
        scraper = jus.scraper("datajud")
        scraper.listar_processos(tribunal="TJAC", numero_processo=CNJ_FORMATADO_TJAC)

        nproc = _numero_processo_no_payload(captured_payloads[0])
        assert all(n.isdigit() for n in nproc)
        assert nproc == [CNJ_LIMPO_TJAC]

    def test_tribunal_mais_lista_formatada(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.listar_processos(
            tribunal="TJAC",
            numero_processo=[CNJ_FORMATADO_TJAC, "0003326-88.2014.8.01.0001"],
        )

        nproc = _numero_processo_no_payload(captured_payloads[0])
        assert nproc == [CNJ_LIMPO_TJAC, "00033268820148010001"]
