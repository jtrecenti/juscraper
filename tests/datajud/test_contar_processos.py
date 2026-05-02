"""Testa ``DatajudScraper.contar_processos`` — contagem sem download.

A intenção do método é a análise de viabilidade: descobrir o volume de
processos para um conjunto de filtros antes de pagar uma raspagem completa.
A implementação reutiliza o mesmo schema e a mesma lógica de resolução de
alias do ``listar_processos``, apenas trocando o payload por
``size=0 + track_total_hits=True``.
"""

from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client


@pytest.fixture
def captured_payloads(monkeypatch):
    """Intercepta ``call_datajud_api`` e devolve uma resposta sintética."""
    payloads = []

    def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
        payloads.append({"alias": alias, "payload": query_payload})
        return {"hits": {"total": {"value": 12345, "relation": "eq"}, "hits": []}}

    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
    return payloads


class TestPayloadShape:
    """O payload de contagem precisa ser ``size=0 + track_total_hits``;
    sem ``sort`` (não há paginação), sem ``_source`` (não há doc baixado)."""

    def test_payload_size_zero_e_track_total_hits(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", ano_ajuizamento=2023)

        assert len(captured_payloads) == 1
        payload = captured_payloads[0]["payload"]
        assert payload["size"] == 0
        assert payload["track_total_hits"] is True
        assert "sort" not in payload
        assert "_source" not in payload

    def test_payload_sem_filtros_eh_match_all(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP")

        payload = captured_payloads[0]["payload"]
        assert payload["query"] == {"match_all": {}}

    def test_payload_combina_classe_e_assuntos(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(
            tribunal="TJSP", classe="436", assuntos=["7780", "1127"]
        )

        payload = captured_payloads[0]["payload"]
        must = payload["query"]["bool"]["must"]
        assert {"match": {"classe.codigo": "436"}} in must
        assert {"terms": {"assuntos.codigo": ["7780", "1127"]}} in must

    def test_payload_ano_ajuizamento_dual_range(self, captured_payloads):
        """Igual ao ``listar_processos``: range ISO + compacto OR-ed."""
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", ano_ajuizamento=2023)

        payload = captured_payloads[0]["payload"]
        must = payload["query"]["bool"]["must"]
        ano_clause = next(c for c in must if "bool" in c)
        shoulds = ano_clause["bool"]["should"]
        assert any(s["range"]["dataAjuizamento"]["gte"] == "2023-01-01" for s in shoulds)
        assert any(s["range"]["dataAjuizamento"]["gte"] == "20230101000000" for s in shoulds)


class TestReturnShape:
    def test_dataframe_uma_linha_por_tribunal(self, captured_payloads):
        scraper = jus.scraper("datajud")
        df = scraper.contar_processos(tribunal="TJSP", ano_ajuizamento=2023)

        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["tribunal", "alias", "count", "relation", "error"]
        assert len(df) == 1
        row = df.iloc[0]
        assert row["tribunal"] == "TJSP"
        assert row["alias"] == "api_publica_tjsp"
        assert row["count"] == 12345
        assert row["relation"] == "eq"
        assert row["error"] is None

    def test_falha_de_rede_vira_erro_na_linha(self, monkeypatch):
        """Quando ``call_datajud_api`` devolve None (falha), a linha
        carrega ``count=None`` e ``error`` populado — análise por
        tribunal continua mesmo com falha em um."""

        def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
            return None

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        scraper = jus.scraper("datajud")
        df = scraper.contar_processos(tribunal="TJSP")

        assert len(df) == 1
        row = df.iloc[0]
        assert row["count"] is None
        assert row["error"] is not None
        assert row["relation"] is None

    def test_relation_gte_quando_truncado(self, monkeypatch):
        def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
            return {"hits": {"total": {"value": 10000, "relation": "gte"}}}

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        scraper = jus.scraper("datajud")
        df = scraper.contar_processos(tribunal="TJSP")
        assert df.iloc[0]["relation"] == "gte"
        assert df.iloc[0]["count"] == 10000


class TestFiltrosNovos176:
    """``contar_processos`` ganha paridade com `listar_processos` no escopo
    de #176 — `data_ajuizamento_*`, `tipos_movimentacao`, `movimentos_codigo`,
    `orgao_julgador`, `query`. Validacao e construcao de payload reusam a
    mesma logica do `listar`."""

    def test_data_ajuizamento_inicio_fim_propaga(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(
            tribunal="TJSP",
            data_ajuizamento_inicio="2024-01-01",
            data_ajuizamento_fim="2024-03-31",
        )

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        bool_clause = must[0]["bool"]
        shoulds = bool_clause["should"]
        assert any(
            s["range"]["dataAjuizamento"].get("gte") == "2024-01-01" for s in shoulds
        )
        assert any(
            s["range"]["dataAjuizamento"].get("gte") == "20240101000000" for s in shoulds
        )

    def test_tipos_movimentacao_resolve_codigos_no_terms(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", tipos_movimentacao=["decisao"])

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        terms_clause = next(c for c in must if "terms" in c and "movimentos.codigo" in c["terms"])
        assert isinstance(terms_clause["terms"]["movimentos.codigo"], list)
        assert len(terms_clause["terms"]["movimentos.codigo"]) > 0

    def test_movimentos_codigo_propaga(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", movimentos_codigo=[193, 442])

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        assert {"terms": {"movimentos.codigo": [193, 442]}} in must

    def test_orgao_julgador_propaga(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", orgao_julgador="Vara X")

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        assert {"match": {"orgaoJulgador.nome": "Vara X"}} in must

    def test_query_override_propaga(self, captured_payloads):
        custom = {
            "bool": {
                "must_not": [{"exists": {"field": "orgaoJulgador.nome"}}],
            }
        }
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", query=custom)

        payload = captured_payloads[0]["payload"]
        assert payload["query"] == custom
        assert payload["size"] == 0
        assert payload["track_total_hits"] is True

    def test_query_exclusivo_com_filtros_amigaveis(self):
        scraper = jus.scraper("datajud")
        with pytest.raises(Exception, match="mutuamente exclusivo"):
            scraper.contar_processos(
                tribunal="TJSP",
                query={"match_all": {}},
                ano_ajuizamento=2024,
            )

    def test_data_e_ano_excluem(self):
        scraper = jus.scraper("datajud")
        with pytest.raises(Exception, match="mutuamente exclusivos"):
            scraper.contar_processos(
                tribunal="TJSP",
                ano_ajuizamento=2024,
                data_ajuizamento_inicio="2024-01-01",
            )


class TestCoercaoTipos217:
    """Issue #217: ``assuntos`` aceita int (codigos TPU sao inteiros);
    ``movimentos_codigo`` aceita str (vindo de planilha/CSV). Smoke test
    confirmando que o validator do schema tambem roda em ``contar_processos``,
    nao so em ``listar_processos``."""

    def test_assuntos_aceita_int(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJMG", assuntos=[12503])

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        assert {"terms": {"assuntos.codigo": ["12503"]}} in must

    def test_movimentos_codigo_aceita_str(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJSP", movimentos_codigo=["246"])

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        assert {"terms": {"movimentos.codigo": [246]}} in must


class TestExtraKwargs:
    def test_kwarg_desconhecido_levanta_typeerror(self):
        scraper = jus.scraper("datajud")
        with pytest.raises(TypeError, match="contar_processos"):
            scraper.contar_processos(tribunal="TJSP", parametro_inventado=1)

    def test_paginacao_nao_e_aceita(self):
        """``contar_processos`` não pagina — paginas/tamanho_pagina/
        mostrar_movs viram TypeError. (Sinaliza ao usuário que o método
        certo pra paginação é ``listar_processos``.)"""
        scraper = jus.scraper("datajud")
        for kwarg in ("paginas", "tamanho_pagina", "mostrar_movs"):
            with pytest.raises(TypeError, match="contar_processos"):
                scraper.contar_processos(tribunal="TJSP", **{kwarg: 1})

    def test_sem_tribunal_nem_numero_processo_levanta_valueerror(self):
        scraper = jus.scraper("datajud")
        with pytest.raises(ValueError, match="tribunal.*numero_processo"):
            scraper.contar_processos(ano_ajuizamento=2023)


class TestMultiplosTribunais:
    """Quando a entrada é uma lista de CNJs de tribunais diferentes, o
    DataFrame resultante traz uma linha por tribunal — facilitando a
    análise de viabilidade transversal."""

    def test_lista_de_cnjs_de_tribunais_diferentes(self, monkeypatch):
        chamadas = []

        def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
            chamadas.append(alias)
            return {
                "hits": {"total": {"value": len(alias), "relation": "eq"}, "hits": []}
            }

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        scraper = jus.scraper("datajud")
        # 1 CNJ TJAC + 1 CNJ TJSP — devem virar 2 chamadas, 2 linhas no df
        cnj_tjac = "00033258820148010001"  # id_justica=8, id_tribunal=01 → TJAC
        cnj_tjsp = "01234567820238260001"  # id_justica=8, id_tribunal=26 → TJSP
        df = scraper.contar_processos(numero_processo=[cnj_tjac, cnj_tjsp])

        assert len(chamadas) == 2
        assert len(df) == 2
        # Cada linha deve referir-se ao tribunal certo
        assert set(df["alias"].tolist()) == {"api_publica_tjac", "api_publica_tjsp"}
