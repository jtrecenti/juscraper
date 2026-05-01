"""Garante que o payload Elasticsearch enviado por listar_processos sempre
carrega `numeroProcesso` apenas com dígitos, em todos os caminhos de entrada
(refs #60).

Inclui também testes granulares do ``build_listar_processos_payload`` para
os filtros novos da issue #49 (data_ajuizamento_*, movimentos_codigo,
orgao_julgador, query-override).
"""
import pytest

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.aggregators.datajud.download import build_listar_processos_payload

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


class TestBuildPayloadFiltrosFlexiveis:
    """Testes granulares de ``build_listar_processos_payload`` para os
    filtros novos da issue #49. Independem do client — chamam o builder
    direto e inspecionam o payload Elasticsearch resultante."""

    def test_data_ajuizamento_dual_format_completo(self):
        payload = build_listar_processos_payload(
            data_ajuizamento_inicio="2024-01-15",
            data_ajuizamento_fim="2024-03-31",
            tamanho_pagina=10,
        )
        must = payload["query"]["bool"]["must"]
        assert len(must) == 1
        bool_clause = must[0]["bool"]
        assert bool_clause["minimum_should_match"] == 1
        should = bool_clause["should"]
        assert len(should) == 2
        # ISO range
        assert should[0]["range"]["dataAjuizamento"] == {
            "gte": "2024-01-15",
            "lte": "2024-03-31",
        }
        # Compact range — note os sufixos 000000 / 235959 cobrindo o dia inteiro.
        assert should[1]["range"]["dataAjuizamento"] == {
            "gte": "20240115000000",
            "lte": "20240331235959",
        }

    def test_data_ajuizamento_apenas_inicio(self):
        payload = build_listar_processos_payload(
            data_ajuizamento_inicio="2024-01-15",
            tamanho_pagina=10,
        )
        bool_clause = payload["query"]["bool"]["must"][0]["bool"]
        should = bool_clause["should"]
        assert should[0]["range"]["dataAjuizamento"] == {"gte": "2024-01-15"}
        assert should[1]["range"]["dataAjuizamento"] == {"gte": "20240115000000"}

    def test_data_ajuizamento_apenas_fim(self):
        payload = build_listar_processos_payload(
            data_ajuizamento_fim="2024-03-31",
            tamanho_pagina=10,
        )
        bool_clause = payload["query"]["bool"]["must"][0]["bool"]
        should = bool_clause["should"]
        assert should[0]["range"]["dataAjuizamento"] == {"lte": "2024-03-31"}
        assert should[1]["range"]["dataAjuizamento"] == {"lte": "20240331235959"}

    def test_movimentos_codigo(self):
        payload = build_listar_processos_payload(
            movimentos_codigo=[193, 442, 12164],
            tamanho_pagina=10,
        )
        must = payload["query"]["bool"]["must"]
        assert must == [{"terms": {"movimentos.codigo": [193, 442, 12164]}}]

    def test_orgao_julgador(self):
        payload = build_listar_processos_payload(
            orgao_julgador="Vara Civel de Brasilia",
            tamanho_pagina=10,
        )
        must = payload["query"]["bool"]["must"]
        assert must == [{"match": {"orgaoJulgador.nome": "Vara Civel de Brasilia"}}]

    def test_query_override_passthrough(self):
        custom_query = {
            "bool": {
                "must_not": [{"exists": {"field": "orgaoJulgador.nome"}}],
                "should": [{"match": {"classe.nome": "tutela"}}],
                "minimum_should_match": 1,
            }
        }
        payload = build_listar_processos_payload(
            query=custom_query,
            tamanho_pagina=50,
        )
        # query e literalmente o dict passado, sem wrapping em bool.must.
        assert payload["query"] is custom_query
        # Outros campos do payload continuam normais (size/sort/_source).
        assert payload["size"] == 50
        assert payload["sort"] == [{"id.keyword": "asc"}]
        assert payload["track_total_hits"] is True
        assert payload["_source"] == {"excludes": ["movimentacoes", "movimentos"]}

    def test_query_override_ignora_outros_filtros_no_builder(self):
        # Defesa em profundidade: mesmo se um caller futuro chamar o builder
        # direto sem passar pelo schema, ``query`` ganha. Os filtros amigaveis
        # nao vazam pra dentro da query custom.
        custom_query: dict = {"match_all": {}}
        payload = build_listar_processos_payload(
            query=custom_query,
            numero_processo="00000000000000000001",
            ano_ajuizamento=2023,
            classe="436",
            assuntos=["1127"],
            data_ajuizamento_inicio="2024-01-01",
            movimentos_codigo=[193],
            orgao_julgador="Vara X",
            tamanho_pagina=10,
        )
        assert payload["query"] == {"match_all": {}}

    def test_combinacao_filtros_amigaveis_ordem_canonica(self):
        # Confirma a ordem documentada na docstring do builder:
        # numero_processo, data, classe, assuntos, movimentos, orgao.
        payload = build_listar_processos_payload(
            numero_processo="00000000000000000001",
            data_ajuizamento_inicio="2024-01-01",
            data_ajuizamento_fim="2024-03-31",
            classe="436",
            assuntos=["1127"],
            movimentos_codigo=[193],
            orgao_julgador="Vara X",
            tamanho_pagina=10,
        )
        must = payload["query"]["bool"]["must"]
        assert len(must) == 6
        assert "terms" in must[0] and "numeroProcesso" in must[0]["terms"]
        assert "bool" in must[1]  # range bool.should para datas
        assert must[2] == {"match": {"classe.codigo": "436"}}
        assert must[3] == {"terms": {"assuntos.codigo": ["1127"]}}
        assert must[4] == {"terms": {"movimentos.codigo": [193]}}
        assert must[5] == {"match": {"orgaoJulgador.nome": "Vara X"}}
