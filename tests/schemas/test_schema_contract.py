"""Contrato generico exercitando cada schema pydantic mapeado.

Complementa os testes pontuais (:mod:`tests.schemas.test_cjsg_schemas`) com
afirmacoes que valem para **todo** schema Input/Output mapeado em
:mod:`tests.schemas._registro`:

- todo ``Input*`` instancia com o payload minimo dos campos obrigatorios
  (:func:`tests.schemas._registro.payload_minimo`);
- todo ``Input*`` rejeita um kwarg desconhecido com ``extra_forbidden``;
- todo ``Output*`` guarda uma coluna extra em ``model_extra`` (``extra="allow"``).

Os testes individuais mais detalhados (defaults, Literals, campos rejeitados
por tribunal especifico) continuam em :mod:`tests.schemas.test_cjsg_schemas`
para o conjunto wired.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tests.schemas._registro import INPUT_SCHEMAS, OUTPUT_SCHEMAS, payload_minimo, schemas_mapeados

INPUT_CASES = schemas_mapeados(INPUT_SCHEMAS)
OUTPUT_CASES = schemas_mapeados(OUTPUT_SCHEMAS)


@pytest.mark.parametrize("par", INPUT_CASES, ids=[p.id for p in INPUT_CASES])
def test_input_rejects_unknown_kwarg(par):
    """Todo Input mapeado rejeita um kwarg desconhecido com ``extra_forbidden``."""
    payload = payload_minimo(par.schema)
    payload["_parametro_que_nao_existe_"] = "x"
    with pytest.raises(ValidationError) as exc_info:
        par.schema(**payload)
    assert any(
        err["type"] == "extra_forbidden" for err in exc_info.value.errors()
    ), f"{par.classe} aceitou _parametro_que_nao_existe_ (extra_forbidden esperado)"


@pytest.mark.parametrize("par", INPUT_CASES, ids=[p.id for p in INPUT_CASES])
def test_input_minimum_payload_instantiable(par):
    """Todo Input mapeado e instanciavel com o minimo de campos requeridos."""
    payload = payload_minimo(par.schema)
    try:
        model = par.schema(**payload)
    except ValidationError as exc:
        pytest.fail(
            f"{par.classe} nao instancia com payload minimo {payload}:\n{exc}"
        )
    assert model is not None


@pytest.mark.parametrize("par", OUTPUT_CASES, ids=[p.id for p in OUTPUT_CASES])
def test_output_allows_extras(par):
    """Todo Output mapeado guarda colunas nao listadas em ``model_extra`` (``extra="allow"``)."""
    payload = payload_minimo(par.schema)
    payload["coluna_especifica_do_tribunal_x"] = "foo"
    model = par.schema(**payload)
    assert model.model_extra == {"coluna_especifica_do_tribunal_x": "foo"}
