"""Teste de aceitacao do parametro ``paginas`` em todos os raspadores.

:class:`juscraper.schemas.PaginasMixin` e a fonte unica do contrato: ``int``,
``list[int]``, ``range`` ou ``None``. Os casos saem dos schemas mapeados que
herdam o mixin, e o teste confere:

1. :func:`juscraper.utils.params.normalize_paginas` aceita as quatro formas e
   rejeita com ``TypeError`` o que estiver fora do contrato.
2. Cada schema paginado aceita as quatro formas.
3. O metodo publico expoe ``paginas`` se e somente se o schema herda o mixin, e
   todo endpoint de busca (``cjsg``, ``cjpg``, ``pesquisa``, ``listar_*``) o herda.
   A anotacao do parametro fica com :mod:`tests.schemas.test_signature_types`.

Testar as pecas separadamente evita chamar cada metodo de ponta a ponta (captcha,
sessao HTTP, diretorios temporarios). Se o schema aceita e o metodo expoe o
parametro, o metodo aceita por composicao.
"""
from __future__ import annotations

from typing import Any, get_args, get_origin

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError

from juscraper.schemas import PaginasMixin
from juscraper.utils.pagination import selecao_de_paginas
from juscraper.utils.params import normalize_paginas
from tests.schemas._registro import parametros_explicitos, payload_minimo, schemas_definidos, schemas_mapeados

PAGINAS_VARIANTS: list[tuple[str, Any]] = [
    ("int", 1),
    ("list", [1]),
    ("range", range(1, 2)),
    ("none", None),
]

TODOS = schemas_mapeados()
#: Endpoints paginados: os de schema com :class:`PaginasMixin`.
SEARCH_CASES = [par for par in TODOS if issubclass(par.schema, PaginasMixin)]


def _e_busca(endpoint: str) -> bool:
    return endpoint in {"cjsg", "cjpg", "pesquisa"} or endpoint.startswith("listar_")


def test_endpoint_de_busca_e_paginado():
    """Busca (``cjsg``, ``cjpg``, ``pesquisa``, ``listar_*``) tem schema com :class:`PaginasMixin`.

    Sem isso, um schema de busca que perdesse o mixin, junto com o ``paginas`` do
    metodo, sairia de ``SEARCH_CASES`` sem nenhum teste reprovar.
    """
    soltos = sorted(
        par.id for par in TODOS if _e_busca(par.endpoint) and not issubclass(par.schema, PaginasMixin)
    )
    assert not soltos, f"Endpoints de busca sem PaginasMixin: {soltos}"


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
def test_paginas_normalizadas_equivale_a_normalize_paginas(paginas, esperado):
    inp = PaginasMixin(paginas=paginas)

    assert esperado == normalize_paginas(paginas)
    # O raspador lê a seleção opaca, com o mesmo conteúdo da normalização.
    assert inp.paginas_normalizadas == selecao_de_paginas(esperado)
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


def _schemas_com_paginas() -> list[type[BaseModel]]:
    """Todo modelo pydantic dos modulos de schemas com campo ``paginas``."""
    return sorted(
        (obj for obj in schemas_definidos() if obj is not PaginasMixin and "paginas" in obj.model_fields),
        key=lambda obj: f"{obj.__module__}.{obj.__qualname__}",
    )


@pytest.mark.parametrize("schema_cls", _schemas_com_paginas(), ids=lambda c: c.__name__)
def test_schema_com_paginas_herda_paginas_mixin(schema_cls):
    """Quem declara ``paginas`` sem o mixin perde o validador (``paginas=0`` passa)."""
    assert issubclass(schema_cls, PaginasMixin)
    field = schema_cls.model_fields["paginas"]
    assert field.annotation == PaginasMixin.model_fields["paginas"].annotation


@pytest.mark.parametrize(("par", "variant_name", "paginas_value"), SCHEMA_CASES)
def test_schema_accepts_paginas(par, variant_name, paginas_value):
    """Todo Input<Endpoint><Tribunal> declara ``paginas`` e o aceita nas 4 formas."""
    schema_cls = par.schema
    assert "paginas" in schema_cls.model_fields, f"{par.classe} nao declara campo ``paginas``"

    kwargs = payload_minimo(schema_cls)
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


@pytest.mark.parametrize("par", TODOS, ids=[par.id for par in TODOS])
def test_metodo_expoe_paginas_sse_schema_e_paginado(par):
    """O metodo publico expoe ``paginas`` se e somente se o schema herda :class:`PaginasMixin`.

    Schema paginado com metodo sem ``paginas`` aceita o campo e o ignora (ou o
    recusa com mensagem confusa); metodo com ``paginas`` e schema sem o mixin
    perde o validador. :mod:`tests.schemas.test_signature_types` confere a anotacao.
    """
    method = getattr(par.raspador, par.endpoint)
    expoe = "paginas" in parametros_explicitos(method)
    paginado = issubclass(par.schema, PaginasMixin)
    assert expoe == paginado, (
        f"{par.raspador.__name__}.{par.endpoint}: parametro ``paginas`` {'sim' if expoe else 'nao'}, "
        f"{par.classe} {'herda' if paginado else 'nao herda'} PaginasMixin"
    )
