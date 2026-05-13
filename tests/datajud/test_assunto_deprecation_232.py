"""Deprecacao do alias plural ``assuntos`` no Datajud (refs #232).

Garante que:

1. ``assuntos`` (plural) ainda funciona, emitindo ``DeprecationWarning`` e
   produzindo o mesmo body Elasticsearch que o singular ``assunto``.
2. Passar ``assunto`` e ``assuntos`` juntos -> :class:`ValueError`.

Aplica-se a ``listar_processos`` e ``contar_processos``.
"""
from __future__ import annotations

import pytest
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from tests._helpers import load_sample
from tests.fixtures.capture.datajud import build_payload as _payload

BASE = "https://api-publica.datajud.cnj.jus.br"


@pytest.fixture
def _captured_payloads(monkeypatch):
    payloads = []

    def fake_call(*, base_url, alias, api_key, session, query_payload, verbose=False):
        payloads.append(query_payload)
        return {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}

    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)
    return payloads


@responses.activate
def test_listar_processos_assuntos_plural_emite_deprecation_warning(mocker):
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        f"{BASE}/api_publica_tjmg/_search",
        body=load_sample("datajud", "listar_processos/single_page.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(_payload(assunto=["12503"], tamanho_pagina=10))],
    )
    with pytest.warns(DeprecationWarning, match=r"'assuntos' .* 'assunto'"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJMG",
            assuntos=[12503],
            tamanho_pagina=10,
            paginas=range(1, 2),
        )


def test_listar_processos_assunto_e_assuntos_juntos_levanta_value_error():
    with pytest.raises(ValueError, match=r"'assunto' e 'assuntos' simultaneamente"):
        jus.scraper("datajud").listar_processos(
            tribunal="TJMG",
            assunto=[12503],
            assuntos=[5885],
        )


def test_contar_processos_assuntos_plural_emite_deprecation_warning(_captured_payloads):
    """``contar_processos(assuntos=...)`` continua funcionando com warning."""
    scraper = jus.scraper("datajud")
    with pytest.warns(DeprecationWarning, match=r"'assuntos' .* 'assunto'"):
        scraper.contar_processos(tribunal="TJMG", assuntos=[12503])
    # Body Elasticsearch usa "assuntos.codigo" (backend); o alias deprecado
    # nao deve alterar o payload.
    must = _captured_payloads[0]["query"]["bool"]["must"]
    assert {"terms": {"assuntos.codigo": ["12503"]}} in must


def test_contar_processos_assunto_e_assuntos_juntos_levanta_value_error():
    with pytest.raises(ValueError, match=r"'assunto' e 'assuntos' simultaneamente"):
        jus.scraper("datajud").contar_processos(
            tribunal="TJMG", assunto=[12503], assuntos=[5885]
        )
