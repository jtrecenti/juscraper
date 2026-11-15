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
import requests

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import RetryExhaustedError

CNJ_TJSP = "0000001-02.2024.8.26.0100"
CNJ_TJRS = "0000001-02.2024.8.21.0001"
CNJ_TJRJ = "0000001-02.2024.8.19.0001"


@pytest.fixture(autouse=True)
def pausas(monkeypatch) -> list[float]:
    """Registra o ``sleep_time`` entre tribunais, sem dormir."""
    registradas: list[float] = []
    monkeypatch.setattr(datajud_client.time, "sleep", registradas.append)
    return registradas


@pytest.fixture
def captured_payloads(monkeypatch):
    """Intercepta ``call_datajud_api`` e devolve uma resposta sintética."""
    payloads = []

    def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
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

    def test_payload_combina_classe_e_assunto(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(
            tribunal="TJSP", classe="436", assunto=["7780", "1127"]
        )

        payload = captured_payloads[0]["payload"]
        must = payload["query"]["bool"]["must"]
        assert {"match": {"classe.codigo": "436"}} in must
        # Chave do payload Elasticsearch fica "assuntos.codigo" (backend);
        # parametro Python e "assunto" (singular, refs #232).
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
        """Quando ``call_datajud_api`` levanta, a linha carrega
        ``count=<NA>`` e ``error`` com o status HTTP — análise por
        tribunal continua mesmo com falha em um."""

        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
            resposta = requests.Response()
            resposta.status_code = 404
            raise requests.HTTPError("404 Client Error", response=resposta)

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        scraper = jus.scraper("datajud")
        df = scraper.contar_processos(tribunal="TJSP")

        assert len(df) == 1
        row = df.iloc[0]
        assert row["count"] is pd.NA
        assert row["error"] == "http_404"
        assert row["relation"] is None

    @pytest.mark.parametrize(
        ("erro", "esperado"),
        [
            (RetryExhaustedError(status_code=429, attempts=3), "retry_esgotado_429"),
            (requests.ReadTimeout("lento"), "timeout"),
            (requests.ConnectTimeout("sem rota"), "conexao"),
            (requests.ConnectionError("recusada"), "conexao"),
            # ``response.json()`` de um 200 que não é JSON; antes saía
            # ``"JSONDecodeError: Expecting value: ..."``.
            (requests.JSONDecodeError("Expecting value", "<html>", 0), "json_invalido"),
            # Fora do vocabulário de ``motivo_falha``: classe e mensagem.
            (requests.TooManyRedirects("laço"), "TooManyRedirects: laço"),
        ],
    )
    def test_coluna_error_usa_o_vocabulario_de_motivo_falha(self, monkeypatch, erro, esperado):
        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
            raise erro

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        row = jus.scraper("datajud").contar_processos(tribunal="TJSP").iloc[0]

        assert row["count"] is pd.NA
        assert row["error"] == esperado

    def test_count_fica_inteiro_quando_outra_linha_falha(self, monkeypatch):
        """Com ``None`` misturado a ``int``, ``count`` virava float (``12345.0``)."""
        respostas = iter([
            {"hits": {"total": {"value": 12345, "relation": "eq"}}},
            requests.ReadTimeout("lento"),
        ])

        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
            resposta = next(respostas)
            if isinstance(resposta, Exception):
                raise resposta
            return resposta

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        df = jus.scraper("datajud").contar_processos(numero_processo=[CNJ_TJSP, CNJ_TJRS])

        assert df["count"].dtype == "Int64"
        assert df["count"].tolist() == [12345, pd.NA]
        assert df["error"].tolist() == [None, "timeout"]

    def test_sem_tribunal_valido_devolve_as_colunas(self):
        with pytest.warns(UserWarning, match="CNJ inválido"):
            df = jus.scraper("datajud").contar_processos(numero_processo=["123"])

        assert df.empty
        assert list(df.columns) == ["tribunal", "alias", "count", "relation", "error"]
        assert df["count"].dtype == "Int64"

    def test_401_interrompe_a_contagem_com_as_falhas_anteriores(self, monkeypatch, pausas):
        """Chave inválida vale para todos os tribunais: propaga, como no JusBR e na PDPJ.

        Antes, cada tribunal virava uma linha ``http_401``, com a pausa entre
        eles, e um lote grande com a chave errada demorava sem necessidade.
        """
        resposta_401 = requests.Response()
        resposta_401.status_code = 401
        erros = iter([requests.ReadTimeout("lento"), requests.HTTPError("401", response=resposta_401)])
        consultados: list[str] = []

        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
            consultados.append(alias)
            raise next(erros)

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

        with pytest.raises(requests.HTTPError) as info:
            jus.scraper("datajud").contar_processos(numero_processo=[CNJ_TJSP, CNJ_TJRS, CNJ_TJRJ])

        assert info.value.response.status_code == 401
        assert consultados == ["api_publica_tjsp", "api_publica_tjrs"]
        assert info.value.__notes__ == [
            "Antes do 401, 1 contagem(ns) de tribunal falharam. Falhas: api_publica_tjsp: timeout."
        ]
        assert len(pausas) == 1

    def test_relation_gte_quando_truncado(self, monkeypatch):
        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
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
    """Issue #217: ``assunto`` aceita int (codigos TPU sao inteiros);
    ``movimentos_codigo`` aceita str (vindo de planilha/CSV). Smoke test
    confirmando que o validator do schema tambem roda em ``contar_processos``,
    nao so em ``listar_processos``."""

    def test_assunto_aceita_int(self, captured_payloads):
        scraper = jus.scraper("datajud")
        scraper.contar_processos(tribunal="TJMG", assunto=[12503])

        must = captured_payloads[0]["payload"]["query"]["bool"]["must"]
        # Chave Elasticsearch fica "assuntos.codigo" (backend); param Python
        # e "assunto". Refs #232.
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
        with pytest.raises(ValueError, match=r"tribunal.*numero_processo"):
            scraper.contar_processos(ano_ajuizamento=2023)


class TestMultiplosTribunais:
    """Quando a entrada é uma lista de CNJs de tribunais diferentes, o
    DataFrame resultante traz uma linha por tribunal — facilitando a
    análise de viabilidade transversal."""

    def test_lista_de_cnjs_de_tribunais_diferentes(self, monkeypatch):
        chamadas = []

        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
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

    def test_pausa_entre_tribunais_inclusive_depois_de_falha(self, monkeypatch):
        eventos: list[str] = []

        def fake_call(*, base_url, alias, api_key, requisitar, query_payload, verbose=False):
            eventos.append(alias)
            if alias == "api_publica_tjac":
                raise requests.ConnectionError("recusada")
            return {"hits": {"total": {"value": 1, "relation": "eq"}, "hits": []}}

        monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
        monkeypatch.setattr(datajud_client.time, "sleep", lambda segundos: eventos.append(f"pausa {segundos}"))

        jus.scraper("datajud", sleep_time=0.7).contar_processos(
            numero_processo=["00033258820148010001", "01234567820238260001"],
        )

        # A pausa vem antes do tribunal seguinte, também depois do que falhou,
        # e não há pausa depois do último.
        assert eventos == ["api_publica_tjac", "pausa 0.7", "api_publica_tjsp"]
