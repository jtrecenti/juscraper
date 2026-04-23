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

Testar as duas pecas separadamente e mais direto e robusto do que
chamar cada metodo publico end-to-end (alguns scrapers abrem diretorios
temporarios, fazem setup de captcha, iniciam sessao HTTP etc. — ruido
que nao e deste teste). Se uma peca aceitou e a outra tambem, o metodo
publico aceita por composicao.

Casos conhecidos de drift contra o contrato entram como ``xfail`` e
viram issues separadas a corrigir em PR proprio — e.g. DataJud
``listar_processos`` so aceita ``range``.
"""
from __future__ import annotations

import importlib
import inspect
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from juscraper.utils.params import normalize_paginas
from tests.schemas.test_schema_coverage import (
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    _iter_aggregator_scrapers,
    _iter_court_scrapers,
)

SEARCH_ENDPOINTS = frozenset({"cjsg", "cjpg", "listar_processos"})

PAGINAS_VARIANTS: list[tuple[str, Any]] = [
    ("int", 1),
    ("list", [1]),
    ("range", range(1, 2)),
    ("none", None),
]

XFAIL_CASES: dict[tuple[str, str, str], str] = {
    ("datajud", "listar_processos", "int"): (
        "DataJud listar_processos aceita apenas ``range`` na assinatura "
        "do client. Contrato de SearchBase exige int/list/None tambem. "
        "Correcao em #118."
    ),
    ("datajud", "listar_processos", "list"): (
        "DataJud listar_processos aceita apenas ``range`` na assinatura "
        "do client. Correcao em #118."
    ),
}


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


def _resolve_schema(module_path: str, class_name: str) -> type[BaseModel]:
    mod = importlib.import_module(module_path)
    schema_cls: type[BaseModel] = getattr(mod, class_name)
    return schema_cls


def _resolve_method(scraper_cls: type, endpoint: str):
    return getattr(scraper_cls, endpoint, None)


def _search_cases(expected_map, scraper_iter):
    scrapers = {name: cls for name, cls in scraper_iter()}
    out = []
    for (name, endpoint), (module_path, class_name) in expected_map.items():
        if endpoint not in SEARCH_ENDPOINTS:
            continue
        cls = scrapers.get(name)
        if cls is None:
            continue
        out.append((name, endpoint, cls, module_path, class_name))
    return out


COURT_CASES = _search_cases(EXPECTED_COURT_SCHEMAS, _iter_court_scrapers)
AGGREGATOR_CASES = _search_cases(EXPECTED_AGGREGATOR_SCHEMAS, _iter_aggregator_scrapers)

SCHEMA_CASES = [
    pytest.param(
        name, endpoint, module_path, class_name, variant_name, paginas_value,
        id=f"{name}.{endpoint}.schema.{variant_name}",
    )
    for name, endpoint, _cls, module_path, class_name in COURT_CASES + AGGREGATOR_CASES
    for variant_name, paginas_value in PAGINAS_VARIANTS
]

SIGNATURE_CASES = [
    pytest.param(
        name, endpoint, cls, variant_name, paginas_value,
        id=f"{name}.{endpoint}.signature.{variant_name}",
    )
    for name, endpoint, cls, _mp, _cn in COURT_CASES + AGGREGATOR_CASES
    for variant_name, paginas_value in PAGINAS_VARIANTS
]


@pytest.mark.parametrize(
    "variant_name,paginas_value",
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


@pytest.mark.parametrize(
    "name,endpoint,module_path,class_name,variant_name,paginas_value",
    SCHEMA_CASES,
)
def test_schema_accepts_paginas(
    name, endpoint, module_path, class_name, variant_name, paginas_value
):
    """Todo Input<Endpoint><Tribunal> aceita ``paginas`` em qualquer das 4 formas."""
    xfail_reason = XFAIL_CASES.get((name, endpoint, variant_name))
    if xfail_reason:
        pytest.xfail(xfail_reason)

    schema_cls = _resolve_schema(module_path, class_name)
    if "paginas" not in schema_cls.model_fields:
        pytest.skip(f"{class_name} nao declara campo ``paginas``")

    kwargs = _minimal_kwargs_for_schema(schema_cls)
    kwargs["paginas"] = paginas_value

    try:
        schema_cls(**kwargs)
    except ValidationError as exc:
        errors = [e for e in exc.errors() if "paginas" in e.get("loc", ())]
        if errors:
            pytest.fail(
                f"{class_name} rejeitou paginas={paginas_value!r} ({variant_name}): "
                f"{errors}"
            )
        # Erro em outro campo (fixture/required nao preenchido) — nao e deste teste.
        raise


@pytest.mark.parametrize(
    "name,endpoint,scraper_cls,variant_name,paginas_value",
    SIGNATURE_CASES,
)
def test_public_method_accepts_paginas(
    name, endpoint, scraper_cls, variant_name, paginas_value
):
    """Assinatura do metodo publico declara ``paginas`` em tipo compativel
    com o contrato de :class:`SearchBase` — ``int | list | range | None``.
    """
    xfail_reason = XFAIL_CASES.get((name, endpoint, variant_name))
    if xfail_reason:
        pytest.xfail(xfail_reason)

    method = _resolve_method(scraper_cls, endpoint)
    assert method is not None, f"{scraper_cls.__name__}.{endpoint} nao existe"

    sig = inspect.signature(method)
    if "paginas" not in sig.parameters:
        pytest.fail(
            f"{scraper_cls.__name__}.{endpoint} nao expoe parametro ``paginas`` "
            "— viola o contrato de SearchBase para endpoints de busca."
        )

    annotation = sig.parameters["paginas"].annotation
    # Anotacao e string (``from __future__ import annotations``) ou tipo.
    anno_str = str(annotation).lower()

    # Tipos aceitos: int, list, range, None (Optional). Checa que todos
    # aparecem na anotacao canonica.
    expected_tokens = {
        "int": ("int",),
        "list": ("list",),
        "range": ("range",),
        "none": ("none", "optional"),
    }
    if variant_name in expected_tokens:
        tokens = expected_tokens[variant_name]
        if not any(tok in anno_str for tok in tokens):
            pytest.fail(
                f"{scraper_cls.__name__}.{endpoint} tem anotacao ``paginas: "
                f"{annotation}`` — nao inclui ``{variant_name}`` declarado no "
                f"contrato de SearchBase (int | list | range | None)."
            )
