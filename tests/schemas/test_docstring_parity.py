"""Paridade entre filtros listados na docstring e campos do schema pydantic.

O padrão de ``CONTRIBUTING.md > Docstrings de métodos públicos com kwargs``
exige correspondência entre filtros documentados e campos do schema.
``CASES`` cobre métodos principais; ``DOWNLOAD_REFERENCE_CASES`` cobre
pares de download, que referenciam o principal via ``:meth:`` para evitar
uma segunda lista de filtros sem validação de paridade.
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
    pytest.param(
        "juscraper.aggregators.comunica_cnj.client", "ComunicaCNJScraper", "listar_comunicacoes",
        "juscraper.aggregators.comunica_cnj.schemas", "InputListarComunicacoesComunicaCNJ",
        id="comunica_cnj.listar_comunicacoes",
    ),
    pytest.param(
        "juscraper.aggregators.falcao.client", "FalcaoScraper", "listar_decisoes",
        "juscraper.aggregators.falcao.schemas", "InputListarDecisoesFalcao",
        id="falcao.listar_decisoes",
    ),
    pytest.param(
        "juscraper.courts.tjrj.client", "TJRJScraper", "cjsg",
        "juscraper.courts.tjrj.schemas", "InputCJSGTJRJ",
        id="tjrj.cjsg",
    ),
    pytest.param(
        "juscraper.aggregators.datajud.client", "DatajudScraper", "listar_processos",
        "juscraper.aggregators.datajud.schemas", "InputListarProcessosDataJud",
        id="datajud.listar_processos",
    ),
    pytest.param(
        "juscraper.courts.stf.client", "STFScraper", "listar_decisoes",
        "juscraper.courts.stf.schemas", "InputListarDecisoesSTF",
        id="stf.listar_decisoes",
    ),
    pytest.param(
        "juscraper.courts.trf3.client", "TRF3Scraper", "cjsg",
        "juscraper.courts.trf3.cjsg_schemas", "InputCJSGTRF3",
        id="trf3.cjsg",
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

    fields = _schema_filter_fields(schema_module, schema_class)
    # Um nome em ``DEPRECATED_ALIASES`` so e subtraido quando NAO e um campo
    # real do schema do caso atual. Cobre colisoes onde o mesmo nome e
    # alias deprecado em outros tribunais (``query`` -> ``pesquisa``) mas
    # campo real aqui (``query`` no DataJud e o override Elasticsearch).
    bullets = _docstring_bullets(method) - EXPLICIT_PARAMS - (DEPRECATED_ALIASES - fields)

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
        "Atualize uma das duas pontas (ver CONTRIBUTING.md > "
        "Docstrings de métodos públicos com kwargs > Filtros e aliases)."
    )


# Pares cuja docstring referencia o método principal via ``:meth:``.
# CONTRIBUTING.md > Docstrings de métodos públicos com kwargs > Métodos
# de download define o contrato; esses métodos ficam fora de ``CASES``.
DOWNLOAD_REFERENCE_CASES = [
    pytest.param(
        "juscraper.courts._esaj.base", "EsajSearchScraper",
        "cjsg_download", "cjsg",
        id="esaj.cjsg_download",
    ),
    pytest.param(
        "juscraper.courts.tjsp.client", "TJSPScraper",
        "cjsg_download", "cjsg",
        id="tjsp.cjsg_download",
    ),
    pytest.param(
        "juscraper.courts.tjsp.client", "TJSPScraper",
        "cjpg_download", "cjpg",
        id="tjsp.cjpg_download",
    ),
    pytest.param(
        "juscraper.courts.tjrj.client", "TJRJScraper",
        "cjsg_download", "cjsg",
        id="tjrj.cjsg_download",
    ),
    pytest.param(
        "juscraper.aggregators.falcao.client", "FalcaoScraper",
        "listar_decisoes_download", "listar_decisoes",
        id="falcao.listar_decisoes_download",
    ),
    pytest.param(
        "juscraper.courts.trf3.client", "TRF3Scraper",
        "cjsg_download", "cjsg",
        id="trf3.cjsg_download",
    ),
]


@pytest.mark.parametrize(
    "module_path,class_name,download_method,toplevel_method",
    DOWNLOAD_REFERENCE_CASES,
)
def test_download_docstring_references_toplevel(
    module_path, class_name, download_method, toplevel_method,
):
    """Exige a referência ao principal conforme o padrão do CONTRIBUTING.md."""
    mod = importlib.import_module(module_path)
    method = getattr(getattr(mod, class_name), download_method)
    doc = inspect.getdoc(method) or ""
    needle = f":meth:`{toplevel_method}`"
    assert needle in doc, (
        f"{class_name}.{download_method} deve referenciar {needle} "
        f"para a lista de filtros em vez de duplicar bullets.\n"
        "  Ver CONTRIBUTING.md > Docstrings de métodos públicos com kwargs > "
        "Métodos de download."
    )
