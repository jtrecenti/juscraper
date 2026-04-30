"""Paridade entre filtros listados na docstring e campos do schema pydantic.

A regra 1 do ``CLAUDE.md > Docstrings de metodos publicos com **kwargs``
exige que cada filtro citado na docstring exista como campo do schema
pydantic correspondente — e vice-versa, que cada campo do schema esteja
documentado. Sem este teste, a paridade depende so de revisao humana e
silenciosamente apodrece quando alguem adiciona/remove um campo no schema
sem atualizar a docstring (ou inverso).

Cobertura: endpoints **top-level** com ``**kwargs`` documentado seguindo
o template do CLAUDE.md. Os pares ``*_download`` referenciam o top-level
via ``:meth:`` e nao duplicam bullets, entao ficam fora deste teste —
sao cobertos pelo proprio teste do top-level via ``inspect.getdoc``.
"""
from __future__ import annotations

import importlib
import inspect
import re

import pytest

# Aliases deprecados resolvidos *antes* do pydantic. Aparecem em uma
# secao propria da docstring (``Aliases deprecados``) mas nao sao campos
# do schema. Mesma lista que tests/schemas/test_signature_parity.py.
DEPRECATED_ALIASES = frozenset({
    "query", "termo",
    "data_inicio", "data_fim",
    "data_julgamento_de", "data_julgamento_ate",
    "data_publicacao_de", "data_publicacao_ate",
})

# Parametros explicitos da assinatura — citados na docstring na secao
# ``Args:`` mas nao sao filtros via ``**kwargs``.
EXPLICIT_PARAMS = frozenset({"pesquisa", "paginas", "diretorio"})

CASES = [
    pytest.param(
        "juscraper.courts._esaj.base", "EsajSearchScraper", "cjsg",
        "juscraper.courts._esaj.schemas", "InputCJSGEsajPuro",
        id="esaj.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjsp.client", "TJSPScraper", "cjsg",
        "juscraper.courts.tjsp.schemas", "InputCJSGTJSP",
        id="tjsp.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjsp.client", "TJSPScraper", "cjpg",
        "juscraper.courts.tjsp.schemas", "InputCJPGTJSP",
        id="tjsp.cjpg",
    ),
]

# Captura nomes em backticks duplos (RST inline literal). Cobre tanto
# "* ``foo`` (tipo): ..." quanto "* ``foo`` / ``bar``".
_NAME_RE = re.compile(r"``(\w+)``")
_BULLET_LINE_RE = re.compile(r"^\s*\*\s+")
# Limites da regiao "**kwargs:" — qualquer secao de top-level subsequente
# (linha que termina em ":" sem indent, ou "Aliases deprecados ..." que
# o Google docstring formata sem dois pontos no nome canonico).
_SECTION_END_RE = re.compile(
    r"^(Aliases\s+deprecados|Raises|Returns|Exemplo|See\s+also|Yields|Note)",
    re.IGNORECASE,
)


def _docstring_bullets(method) -> set[str]:
    """Extract filter names from bullets in the docstring's ``**kwargs`` section.

    Restringe a varredura a regiao que comeca em ``**kwargs:`` e termina
    na proxima secao top-level (Aliases deprecados, Raises, Returns,
    Exemplo, See also). Em cada bullet, captura apenas os nomes que
    aparecem **antes** do primeiro ``(`` (tipo pydantic) ou ``:``
    (descricao) — assim defaults inline citados em backticks na
    descricao (ex.: True, acordao) nao sao confundidos com nomes de
    filtro.
    """
    doc = inspect.getdoc(method) or ""
    in_kwargs = False
    bullets: set[str] = set()
    for line in doc.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("**kwargs"):
            in_kwargs = True
            continue
        if in_kwargs and not line.startswith(" ") and _SECTION_END_RE.match(line):
            break
        if not (in_kwargs and _BULLET_LINE_RE.match(line)):
            continue
        # Capturar so o "header" do bullet — antes do tipo "(...)"
        # ou da descricao ": ...".
        cut = len(line)
        for delim in ("(", ":"):
            pos = line.find(delim)
            if pos != -1:
                cut = min(cut, pos)
        bullets.update(_NAME_RE.findall(line[:cut]))
    return bullets


def _schema_filter_fields(module_path: str, class_name: str) -> set[str]:
    mod = importlib.import_module(module_path)
    klass = getattr(mod, class_name)
    return set(klass.model_fields.keys()) - EXPLICIT_PARAMS


@pytest.mark.parametrize(
    "scraper_module,scraper_class,endpoint,schema_module,schema_class",
    CASES,
)
def test_docstring_lists_schema_fields(
    scraper_module, scraper_class, endpoint, schema_module, schema_class,
):
    mod = importlib.import_module(scraper_module)
    method = getattr(getattr(mod, scraper_class), endpoint)

    bullets = _docstring_bullets(method) - EXPLICIT_PARAMS - DEPRECATED_ALIASES
    fields = _schema_filter_fields(schema_module, schema_class)

    schema_only = fields - bullets
    docstring_only = bullets - fields

    assert not schema_only and not docstring_only, (
        f"{scraper_class}.{endpoint} — paridade docstring/schema falhou:\n"
        f"  campos no schema {schema_class} mas nao na docstring: "
        f"{sorted(schema_only) or '-'}\n"
        f"  bullets na docstring mas nao no schema: "
        f"{sorted(docstring_only) or '-'}\n"
        f"  schema = {schema_module}:{schema_class}\n"
        f"  metodo = {scraper_class}.{endpoint}\n"
        "Atualize uma das duas pontas (ver CLAUDE.md > "
        "Docstrings de metodos publicos com **kwargs, regra 1)."
    )
