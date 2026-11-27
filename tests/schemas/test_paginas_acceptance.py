"""Teste de aceitacao do parametro ``paginas`` em todos os raspadores.

O contrato de :class:`juscraper.schemas.SearchBase` promete que todo
endpoint de busca aceita ``int``, ``list[int]``, ``range`` ou ``None``
em ``paginas``. Este teste valida as **duas pecas** que decidem essa
aceitacao em qualquer scraper wired ou a wirar:

1. :func:`juscraper.utils.params.normalize_paginas` — converte a entrada
   em um iteravel canonico; rejeita com ``TypeError`` tipos fora do
   contrato.
2. O Input schema pydantic declarado para cada endpoint — valida
   ``paginas`` com a anotacao herdada de :class:`SearchBase`.

Do metodo publico, este teste so exige que exponha ``paginas``; a anotacao
dele e conferida contra o schema por :mod:`tests.schemas.test_signature_types`.

Testar as duas pecas separadamente e mais direto e robusto do que
chamar cada metodo publico end-to-end (alguns scrapers abrem diretorios
temporarios, fazem setup de captcha, iniciam sessao HTTP etc. — ruido
que nao e deste teste). Se uma peca aceitou e a outra tambem, o metodo
publico aceita por composicao.
"""
from __future__ import annotations

import inspect
from typing import Any, get_args, get_origin

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError

from juscraper.schemas import PaginasMixin
from juscraper.utils.params import normalize_paginas
from tests.schemas.test_schema_coverage import (
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    _iter_aggregator_scrapers,
    _iter_court_scrapers,
    _resolve,
    _schemas_mapeados,
)

SEARCH_ENDPOINTS = frozenset({"cjsg", "cjpg", "listar_processos", "listar_decisoes"})

PAGINAS_VARIANTS: list[tuple[str, Any]] = [
    ("int", 1),
    ("list", [1]),
    ("range", range(1, 2)),
    ("none", None),
]

def _minimal_kwargs_for_schema(schema_cls: type[BaseModel]) -> dict[str, Any]:
    """Preenche campos ``required`` do schema com valores neutros."""
    kwargs: dict[str, Any] = {}
    for name, field in schema_cls.model_fields.items():
        if not field.is_required():
            continue
        # Tipos comuns em fields required: str, str | list[str].
        # ``pesquisa``: str; ``id_cnj``: str | list[str]; ``token``: str; ``base_df``: Any.
        kwargs[name] = "teste"
    return kwargs


SEARCH_CASES = [
    par
    for par in _schemas_mapeados(EXPECTED_COURT_SCHEMAS, _iter_court_scrapers)
    + _schemas_mapeados(EXPECTED_AGGREGATOR_SCHEMAS, _iter_aggregator_scrapers)
    if par.endpoint in SEARCH_ENDPOINTS
]

SCHEMA_CASES = [
    pytest.param(par, variant_name, paginas_value, id=f"{par.sigla}.{par.endpoint}.schema.{variant_name}")
    for par in SEARCH_CASES
    for variant_name, paginas_value in PAGINAS_VARIANTS
]


@pytest.mark.parametrize(
    ("variant_name", "paginas_value"),
    PAGINAS_VARIANTS,
    ids=[v[0] for v in PAGINAS_VARIANTS],
)
def test_normalize_paginas_accepts_all_variants(variant_name, paginas_value):
    """``normalize_paginas`` aceita as 4 formas do contrato sem levantar."""
    try:
        normalize_paginas(paginas_value)
    except TypeError as exc:
        pytest.fail(
            f"normalize_paginas rejeitou paginas={paginas_value!r} ({variant_name}): {exc}"
        )


def test_paginas_mixin_validates_large_range_without_scanning():
    paginas = range(1, 100_000_001)
    variants = get_args(PaginasMixin.model_fields["paginas"].annotation)
    range_index = variants.index(range)
    list_index = next(
        index for index, variant in enumerate(variants)
        if get_origin(variant) is list
    )

    result = PaginasMixin(paginas=paginas).paginas

    assert range_index < list_index
    assert result == paginas


@pytest.mark.parametrize(
    ("paginas", "esperado"),
    [(None, None), (3, range(1, 4)), ([2, 4], [2, 4]), (range(2, 5), range(2, 5))],
)
def test_paginas_normalizadas_iguala_normalize_paginas(paginas, esperado):
    inp = PaginasMixin(paginas=paginas)

    assert inp.paginas_normalizadas == esperado == normalize_paginas(paginas)
    # ``paginas`` segue como validado, e a propriedade nao vira campo.
    assert inp.paginas == paginas
    assert "paginas_normalizadas" not in inp.model_dump()


@pytest.mark.parametrize(
    "paginas",
    [0, -1, [], [0], [-1], range(3, 0, -1), True, np.True_, [True], [1, np.True_], (True,)],
)
def test_paginas_mixin_rejects_invalid_selections(paginas):
    with pytest.raises(ValidationError, match="paginas"):
        PaginasMixin(paginas=paginas)


@pytest.mark.parametrize(("par", "variant_name", "paginas_value"), SCHEMA_CASES)
def test_schema_accepts_paginas(par, variant_name, paginas_value):
    """Todo Input<Endpoint><Tribunal> declara ``paginas`` e o aceita nas 4 formas."""
    schema_cls = _resolve(par.modulo, par.classe)
    assert schema_cls is not None, f"{par.modulo}:{par.classe} nao encontrado"
    assert "paginas" in schema_cls.model_fields, f"{par.classe} nao declara campo ``paginas``"

    kwargs = _minimal_kwargs_for_schema(schema_cls)
    kwargs["paginas"] = paginas_value

    try:
        schema_cls(**kwargs)
    except ValidationError as exc:
        errors = [e for e in exc.errors() if "paginas" in e.get("loc", ())]
        if errors:
            pytest.fail(
                f"{par.classe} rejeitou paginas={paginas_value!r} ({variant_name}): "
                f"{errors}"
            )
        # Erro em outro campo (fixture/required nao preenchido) — nao e deste teste.
        raise


@pytest.mark.parametrize(
    "par", SEARCH_CASES, ids=[f"{par.sigla}.{par.endpoint}" for par in SEARCH_CASES]
)
def test_public_method_accepts_paginas(par):
    """Metodo publico de busca expoe ``paginas``, como promete :class:`SearchBase`.

    Com o campo tambem no schema (:func:`test_schema_accepts_paginas`),
    :mod:`tests.schemas.test_signature_types` confere a anotacao.
    """
    method = getattr(par.raspador, par.endpoint)
    assert "paginas" in inspect.signature(method).parameters, (
        f"{par.raspador.__name__}.{par.endpoint} nao expoe parametro ``paginas`` "
        "— viola o contrato de SearchBase para endpoints de busca."
    )
