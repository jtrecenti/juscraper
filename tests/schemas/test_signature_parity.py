"""Paridade entre campos do schema pydantic e parametros do metodo publico.

Para cada ``Input*`` mapeado em :mod:`tests.schemas._registro`, compara os
campos do modelo com os parametros **explicitos** do metodo publico
correspondente. Falha se:

- metodo tem parametro explicito (nao ``**kwargs``, nao infra) que nao
  esta no schema: o schema ficou desatualizado.
- metodo sem ``**kwargs`` e schema tem campo que nao e parametro do metodo:
  o schema vazou. Com ``**kwargs``, o campo pode chegar por ele, e so a
  primeira direcao vale.

Vale para todo endpoint mapeado, inclusive os que validam pelo schema dentro
do metodo (``INPUT_<ENDPOINT>``): assinatura e schema nao podem driftar em
silencio em nenhum deles.
"""
from __future__ import annotations

import pytest

from tests.schemas._registro import SchemaMapeado, aceita_kwargs, parametros_explicitos, schemas_mapeados

# Parametros da assinatura que nao fazem parte da API validada pelo schema.
# ``diretorio`` (destino de download) entra em alguns schemas, mas nao em todos.
INFRA_PARAMS = frozenset({"self", "diretorio"})

CASOS = schemas_mapeados()


@pytest.mark.parametrize("par", CASOS, ids=[par.id for par in CASOS])
def test_schema_bate_com_assinatura_do_metodo(par: SchemaMapeado):
    metodo = getattr(par.raspador, par.endpoint)
    params = parametros_explicitos(metodo) - INFRA_PARAMS
    campos = set(par.schema.model_fields) - INFRA_PARAMS

    schema_tem_a_mais = set() if aceita_kwargs(metodo) else campos - params
    metodo_tem_a_mais = params - campos

    local = f"schema = {par.modulo}:{par.classe}; metodo = {par.raspador.__name__}.{par.endpoint}"
    assert not metodo_tem_a_mais, f"{par.id}: params no metodo mas nao no schema: {sorted(metodo_tem_a_mais)} ({local})"
    assert not schema_tem_a_mais, f"{par.id}: campos no schema mas nao no metodo: {sorted(schema_tem_a_mais)} ({local})"
