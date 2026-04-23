"""Paridade entre campos do schema pydantic e parametros do metodo publico.

Para cada ``Input<Endpoint><Tribunal>`` mapeado em
:mod:`tests.schemas.test_schema_coverage`, compara os campos do modelo
com os parametros **explicitos** do metodo publico correspondente. Falha se:

- schema tem campo que nao e parametro do metodo (nem alias deprecado
  conhecido, nem param de infra): o schema vazou.
- metodo tem parametro explicito (nao ``**kwargs``, nao infra) que nao
  esta no schema: o schema ficou desatualizado.

Para endpoints **wired** (scraper expoe ``INPUT_<ENDPOINT>`` como atributo
de classe e delega aos internals da familia), pular a paridade: o metodo
aceita ``pesquisa``/``paginas``/``**kwargs`` e delega toda a validacao de
filtros para o proprio schema. A paridade seria falsa-negativa.

Este teste e a rede de seguranca dos schemas **nao wired** — impede que
assinatura do metodo e schema-arquivo driftem em silencio ate o tribunal
ser refatorado.
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from tests.schemas.test_schema_coverage import (
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    _iter_aggregator_scrapers,
    _iter_court_scrapers,
)

# Parametros que a assinatura do metodo aceita mas que nao fazem parte
# da API publica de busca/consulta — sao infraestrutura (DI, destino de
# download, etc.). Nao pertencem ao schema pydantic.
INFRA_PARAMS = frozenset(
    {
        "self",
        "session",
        "diretorio",
        "download_path",
        "base_url",
    }
)

# Aliases deprecados resolvidos por ``normalize_pesquisa``/``normalize_datas``
# *antes* do pydantic. Chegam via ``**kwargs`` na assinatura e por isso nao
# aparecem como parametros explicitos — mas se aparecerem (alguns metodos
# listam explicitamente), nao devem estar no schema.
DEPRECATED_ALIASES = frozenset(
    {
        "query",
        "termo",
        "data_inicio",
        "data_fim",
        "data_julgamento_de",
        "data_julgamento_ate",
        "data_publicacao_de",
        "data_publicacao_ate",
    }
)

# Nomes canonicos que o metodo aceita via ``**kwargs`` quando usa
# ``normalize_datas`` (sao parte da API publica, so nao aparecem como
# parametros explicitos na assinatura). Podem figurar no schema.
CANONICAL_KWARGS_ACCEPTED = frozenset(
    {
        "data_julgamento_inicio",
        "data_julgamento_fim",
        "data_publicacao_inicio",
        "data_publicacao_fim",
    }
)


def _explicit_params(method) -> set[str]:
    """Parametros explicitos da assinatura, sem ``self`` / ``**kwargs`` / ``*args``."""
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        return set()
    out: set[str] = set()
    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        out.add(name)
    return out


def _accepts_kwargs(method) -> bool:
    """True se a assinatura aceita ``**kwargs`` (aceita filtros opcionais
    nao listados explicitamente — tipicos em scrapers que usam ``normalize_datas``
    ou delegam para um download manager com mais parametros)."""
    try:
        sig = inspect.signature(method)
    except (ValueError, TypeError):
        return False
    return any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )


def _schema_fields(module_path: str, class_name: str) -> set[str]:
    mod = importlib.import_module(module_path)
    klass = getattr(mod, class_name)
    return set(klass.model_fields.keys())


# Endpoints wired mas sem atributo INPUT_<ENDPOINT> de classe (validacao
# acontece dentro de um metodo irmao ou de um download manager). Na pratica,
# o scraper ja usa o schema pydantic para rejeitar kwargs desconhecidos, mas
# o padrao "INPUT_CJSG = ..." do EsajSearchScraper nao se aplica.
WIRED_WITHOUT_CLASS_ATTR: frozenset[tuple[str, str]] = frozenset(
    {
        ("tjsp", "cjpg"),  # valida dentro de cjpg_download via InputCJPGTJSP
    }
)


def _is_wired(scraper_cls: type, endpoint: str) -> bool:
    """Wired quando o scraper expoe ``INPUT_<ENDPOINT>`` como atributo de classe
    ou esta na lista ``WIRED_WITHOUT_CLASS_ATTR``."""
    if hasattr(scraper_cls, f"INPUT_{endpoint.upper()}"):
        return True
    # Tribunal code e derivado do nome do modulo do scraper
    module_name = scraper_cls.__module__.split(".")[-2]
    return (module_name, endpoint) in WIRED_WITHOUT_CLASS_ATTR


def _build_parity_cases(
    expected_map: dict,
    scraper_iter,
) -> list[tuple[str, str, type, str, str]]:
    scrapers = {name: cls for name, cls in scraper_iter()}
    cases = []
    for (name, endpoint), (module_path, class_name) in expected_map.items():
        cls = scrapers.get(name)
        if cls is None:
            continue
        cases.append((name, endpoint, cls, module_path, class_name))
    return cases


COURT_CASES = _build_parity_cases(EXPECTED_COURT_SCHEMAS, _iter_court_scrapers)
AGG_CASES = _build_parity_cases(EXPECTED_AGGREGATOR_SCHEMAS, _iter_aggregator_scrapers)


@pytest.mark.parametrize(
    "tribunal,endpoint,scraper_cls,module_path,class_name",
    COURT_CASES,
    ids=[f"{t}.{e}" for t, e, _, _, _ in COURT_CASES],
)
def test_court_schema_matches_method_signature(
    tribunal, endpoint, scraper_cls, module_path, class_name
):
    if _is_wired(scraper_cls, endpoint):
        pytest.skip(
            f"{tribunal}.{endpoint} e wired (INPUT_{endpoint.upper()} definido) "
            "— schema e a fonte da verdade, paridade nao se aplica"
        )

    method = getattr(scraper_cls, endpoint)
    params = _explicit_params(method) - INFRA_PARAMS - DEPRECATED_ALIASES
    fields = _schema_fields(module_path, class_name)

    # Quando o metodo aceita ``**kwargs``, schema pode ter mais campos do
    # que a assinatura explicita (filtros que chegam via kwargs). O teste
    # so vigia o outro lado: todo param explicito precisa estar no schema.
    if _accepts_kwargs(method):
        schema_has_extra: set[str] = set()
    else:
        schema_has_extra = fields - params - CANONICAL_KWARGS_ACCEPTED
    method_has_extra = params - fields

    assert not schema_has_extra and not method_has_extra, (
        f"{tribunal}.{endpoint} — paridade falhou:\n"
        f"  campos no schema mas nao no metodo: {sorted(schema_has_extra) or '-'}\n"
        f"  params no metodo mas nao no schema: {sorted(method_has_extra) or '-'}\n"
        f"  schema = {module_path}:{class_name}\n"
        f"  metodo = {scraper_cls.__name__}.{endpoint}"
    )


@pytest.mark.parametrize(
    "name,endpoint,scraper_cls,module_path,class_name",
    AGG_CASES,
    ids=[f"{n}.{e}" for n, e, _, _, _ in AGG_CASES],
)
def test_aggregator_schema_matches_method_signature(
    name, endpoint, scraper_cls, module_path, class_name
):
    if _is_wired(scraper_cls, endpoint):
        pytest.skip(
            f"{name}.{endpoint} e wired — paridade nao se aplica"
        )

    method = getattr(scraper_cls, endpoint)
    params = _explicit_params(method) - INFRA_PARAMS - DEPRECATED_ALIASES
    fields = _schema_fields(module_path, class_name)

    # Quando o metodo aceita ``**kwargs``, schema pode ter mais campos do
    # que a assinatura explicita (filtros que chegam via kwargs). O teste
    # so vigia o outro lado: todo param explicito precisa estar no schema.
    if _accepts_kwargs(method):
        schema_has_extra: set[str] = set()
    else:
        schema_has_extra = fields - params - CANONICAL_KWARGS_ACCEPTED
    method_has_extra = params - fields

    assert not schema_has_extra and not method_has_extra, (
        f"{name}.{endpoint} — paridade falhou:\n"
        f"  campos no schema mas nao no metodo: {sorted(schema_has_extra) or '-'}\n"
        f"  params no metodo mas nao no schema: {sorted(method_has_extra) or '-'}\n"
        f"  schema = {module_path}:{class_name}\n"
        f"  metodo = {scraper_cls.__name__}.{endpoint}"
    )
