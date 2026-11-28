"""Paridade entre filtros listados na docstring e campos do schema pydantic.

O padrão de ``CONTRIBUTING.md > Docstrings de métodos públicos com kwargs``
exige correspondência entre filtros documentados e campos do schema.
``CASES`` cobre métodos principais; ``DOWNLOAD_REFERENCE_CASES`` cobre os
pares de download achados no pacote, que referenciam o principal via ``:meth:`` para evitar
uma segunda lista de filtros sem validação de paridade.
"""
from __future__ import annotations

import importlib
import inspect
import json
import re
import types
import typing
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic_core import PydanticUndefined

from juscraper.utils.params import DATE_CANONICAL
from tests.schemas._registro import ALIASES_DEPRECADOS, aceita_kwargs, modulos, resolve

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
        "juscraper.courts._esaj.cjpg", "EsajCjpgScraper", "cjpg",
        "juscraper.courts._esaj.schemas", "InputCJPGEsaj",
        id="esaj.cjpg",
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
        "juscraper.courts.stm.client", "STMScraper", "cjsg",
        "juscraper.courts.stm.schemas", "InputCJSGSTM",
        id="stm.cjsg",
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
    pytest.param(
        "juscraper.courts.tjdft.client", "TJDFTScraper", "cjsg",
        "juscraper.courts.tjdft.schemas", "InputCJSGTJDFT",
        id="tjdft.cjsg",
    ),
    pytest.param(
        "juscraper.aggregators.pdpj.client", "PdpjScraper", "pesquisa",
        "juscraper.aggregators.pdpj.schemas", "InputPesquisaPdpj",
        id="pdpj.pesquisa",
    ),
    pytest.param(
        "juscraper.aggregators.pdpj.client", "PdpjScraper", "contar",
        "juscraper.aggregators.pdpj.schemas", "InputContarPdpj",
        id="pdpj.contar",
    ),
]

# Captura nomes em backticks duplos (RST inline literal). Cobre tanto
# "* ``foo`` (tipo): ..." quanto "* ``foo`` / ``bar``".
_NAME_RE = re.compile(r"``(\w+)``")
_BULLET_LINE_RE = re.compile(r"^\s*\*\s+")
# Tipo entre parenteses no comeco do texto, que pode ocupar mais de uma linha.
_TYPE_RE = re.compile(r"\(([^)]*)\)")


def _kwargs_bullets(method) -> list[str]:
    """Bullets da seção ``**kwargs:``, cada um com as linhas de continuação.

    A região começa em ``**kwargs:`` e termina na primeira linha sem recuo,
    que é a próxima seção (``Aliases deprecados``, ``Raises``, ``Avisos``...).
    """
    doc = inspect.getdoc(method) or ""
    in_kwargs = False
    bullets: list[str] = []
    recuo = 0
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.startswith("**kwargs"):
            in_kwargs = True
            continue
        if not in_kwargs:
            continue
        if stripped and not line.startswith(" "):
            break
        if _BULLET_LINE_RE.match(line):
            recuo = len(line) - len(line.lstrip())
            bullets.append(_BULLET_LINE_RE.sub("", line))
        elif bullets and stripped and len(line) - len(line.lstrip()) > recuo:
            bullets[-1] += "\n" + stripped
    return bullets


def _docstring_bullets(method) -> dict[str, str | None]:
    """Map filter names to declared types in the docstring's ``**kwargs`` section.

    Em cada bullet, captura apenas os nomes que aparecem **antes** do
    primeiro ``(`` (tipo) ou ``:`` (descrição), para que defaults citados em
    backticks na descrição (ex.: ``True``, ``acordao``) não sejam confundidos
    com nomes de filtro. O tipo é o texto entre os parênteses logo após os
    nomes, ainda que na linha de continuação (ex.: ``int | str``), ou
    ``None`` se o bullet não declara tipo.
    """
    bullets: dict[str, str | None] = {}
    for bullet in _kwargs_bullets(method):
        primeira, _, resto = bullet.partition("\n")
        cut = min((pos for pos in (primeira.find("("), primeira.find(":")) if pos != -1), default=len(primeira))
        # Os nomes ficam na primeira linha; o tipo pode abrir a continuação.
        tipo = _TYPE_RE.match(primeira[cut:] or resto)
        declared = " ".join(tipo.group(1).split()) if tipo else None
        for name in _NAME_RE.findall(primeira[:cut]):
            bullets.setdefault(name, declared)
    return bullets


def _schema_filter_fields(module_path: str, class_name: str) -> set[str]:
    return set(resolve(module_path, class_name).model_fields) - EXPLICIT_PARAMS


@pytest.mark.parametrize(
    ("scraper_module", "scraper_class", "endpoint", "schema_module", "schema_class"),
    CASES,
)
def test_docstring_lists_schema_fields(
    scraper_module, scraper_class, endpoint, schema_module, schema_class,
):
    mod = importlib.import_module(scraper_module)
    method = getattr(getattr(mod, scraper_class), endpoint)

    fields = _schema_filter_fields(schema_module, schema_class)
    # Um nome em ``ALIASES_DEPRECADOS`` so e subtraido quando NAO e um campo
    # real do schema do caso atual. Cobre colisoes onde o mesmo nome e
    # alias deprecado em outros tribunais (``query`` -> ``pesquisa``) mas
    # campo real aqui (``query`` no DataJud e o override Elasticsearch).
    bullets = set(_docstring_bullets(method)) - EXPLICIT_PARAMS - (ALIASES_DEPRECADOS - fields)

    schema_only = fields - bullets
    docstring_only = bullets - fields

    assert not schema_only | docstring_only, (
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


# Campos que ``apply_input_pipeline_search`` converte de ``date``/``datetime``
# em texto antes do pydantic (``coerce_brazilian_date``): a docstring
# acrescenta ``date`` ao tipo do schema; ``datetime`` é subclasse de ``date``.
# O Falcão faz o mesmo em ``data_juntada_*``.
_DATAS_NORMALIZADAS = frozenset(DATE_CANONICAL) | {"data_juntada_inicio", "data_juntada_fim"}

#: Campo que aceita mais do que a anotação do schema, por um
#: ``field_validator(mode="before")`` ou por conversão no cliente antes do
#: pydantic: o tipo que a docstring declara, com o motivo em comentário. A
#: chave é a classe que declara o campo ou o validador (vale para as subclasses).
AMPLIADOS: dict[tuple[str, str], object] = {
    # int, que o field_validator do schema converte em str.
    ("InputCJSGTJRJ", "competencia"): Literal["1", "2", "3", 1, 2, 3] | None,
    ("InputCJSGTJRJ", "origem"): Literal["1", "2", "3", "4", "5", 1, 2, 3, 4, 5],
    ("_InputFiltrosDataJud", "assunto"): list[str | int] | None,
    # str numérica, que o field_validator do schema converte em int.
    ("_InputFiltrosDataJud", "movimentos_codigo"): list[int | str] | None,
}


def _tipo_de_entrada(schema, nome: str) -> object:
    """Tipo que o filtro aceita: o de entrada do validador, se houver, ou a anotação."""
    for classe in schema.__mro__:
        if (classe.__name__, nome) in AMPLIADOS:
            return AMPLIADOS[classe.__name__, nome]
    campo = schema.model_fields[nome]
    for metadado in campo.metadata:
        entrada = getattr(metadado, "json_schema_input_type", PydanticUndefined)
        if entrada is not PydanticUndefined:
            return entrada
    if nome in _DATAS_NORMALIZADAS:
        return campo.annotation | date
    return campo.annotation


def _membros(tipo: object) -> frozenset:
    """Forma comparável de um tipo: a ordem da união e o nome do alias não contam."""
    origem = typing.get_origin(tipo)
    argumentos = typing.get_args(tipo)
    if origem is typing.Annotated:
        return _membros(argumentos[0])
    if origem in (typing.Union, types.UnionType):
        return frozenset().union(*map(_membros, argumentos))
    if origem is Literal:
        return frozenset((type(valor), valor) for valor in argumentos)
    if tipo is None:
        return frozenset({type(None)})
    if origem is not None:
        return frozenset({(origem, tuple(map(_membros, argumentos)))})
    return frozenset({tipo})


def _formatar(tipo: object) -> str:
    """Tipo como a docstring o escreve (``Literal["a", "b"] | None``), para colar da mensagem.

    Percorre as mesmas formas de :func:`_membros`; tipo novo entra nas duas.
    """
    origem = typing.get_origin(tipo)
    argumentos = typing.get_args(tipo)
    if origem is typing.Annotated:
        return _formatar(argumentos[0])
    if origem in (typing.Union, types.UnionType):
        nulo = type(None) in argumentos
        partes = [_formatar(arg) for arg in argumentos if arg is not type(None)]
        return " | ".join(partes + ["None"] * nulo)
    if origem is Literal:
        return "Literal[" + ", ".join(json.dumps(valor, ensure_ascii=False) for valor in argumentos) + "]"
    if tipo is None or tipo is type(None):
        return "None"
    if origem is not None:
        return f"{origem.__name__}[{', '.join(map(_formatar, argumentos))}]"
    return getattr(tipo, "__name__", str(tipo))


def _avaliar(declarado: str, *modulos) -> object:
    """Avalia o tipo escrito na docstring; aceita os aliases dos módulos (ex.: ``BuscarEm``)."""
    nomes: dict[str, object] = {"Any": Any, "Literal": Literal, "Path": Path, "date": date}
    for modulo in modulos:
        nomes.update(vars(modulo))
    return eval(declarado, nomes)


@pytest.mark.parametrize(
    ("scraper_module", "scraper_class", "endpoint", "schema_module", "schema_class"),
    CASES,
)
def test_docstring_declares_schema_types(
    scraper_module, scraper_class, endpoint, schema_module, schema_class,
):
    """O tipo de cada filtro em ``**kwargs`` é o que o schema aceita.

    Esses filtros não têm anotação na assinatura, e a referência publica o
    tipo escrito na docstring. A comparação ignora a ordem da união e aceita
    o nome de um alias (``BuscarEm``) definido no módulo do scraper ou do
    schema no lugar do ``Literal``.
    """
    mod = importlib.import_module(scraper_module)
    schema_mod = importlib.import_module(schema_module)
    method = getattr(getattr(mod, scraper_class), endpoint)
    klass = resolve(schema_module, schema_class)

    wrong = {}
    for name, declared in _docstring_bullets(method).items():
        # Bullet fora do schema fica para test_docstring_lists_schema_fields.
        if name not in klass.model_fields or name in EXPLICIT_PARAMS:
            continue
        expected = _tipo_de_entrada(klass, name)
        try:
            ok = declared is not None and _membros(_avaliar(declared, schema_mod, mod)) == _membros(expected)
        except (SyntaxError, NameError, TypeError):
            ok = False
        if not ok:
            wrong[name] = (declared, _formatar(expected))

    assert not wrong, (
        f"{scraper_class}.{endpoint} — tipo de filtro na docstring diverge do "
        "schema:\n"
        + "".join(
            f"  ``{name}``: docstring ({declared}), esperado ({expected})\n"
            for name, (declared, expected) in sorted(wrong.items())
        )
        + f"  schema = {schema_module}:{schema_class}\n"
        "Campo que aceita mais que a anotação entra em AMPLIADOS, com o motivo."
    )


def _pares_download() -> list[tuple[str, str, str]]:
    """Pares ``*_download`` públicos cujo método principal recebe ``**kwargs``.

    Percorre os módulos do pacote e devolve ``(módulo, classe, método)`` só
    para o método definido na própria classe: o herdado já é coberto pela
    classe que o define. Os pares em ``CASES``, que listam os próprios
    filtros, ficam de fora.
    """
    em_cases = {tuple(p.values[:3]) for p in CASES}
    pares = set()
    for mod in modulos():
        for class_name, klass in vars(mod).items():
            if not inspect.isclass(klass) or klass.__module__ != mod.__name__:
                continue
            for name, attr in vars(klass).items():
                if name.startswith("_") or not name.endswith("_download") or not callable(attr):
                    continue
                principal = getattr(klass, name.removesuffix("_download"), None)
                if principal is not None and aceita_kwargs(principal):
                    pares.add((mod.__name__, class_name, name))
    return sorted(pares - em_cases)


# Pares que remetem ao método principal via ``:meth:``, achados no pacote.
# CONTRIBUTING.md > Docstrings de métodos públicos com kwargs > Métodos
# de download define o contrato; download que lista os próprios filtros
# entra em ``CASES`` e sai daqui.
DOWNLOAD_REFERENCE_CASES = [
    pytest.param(
        module_path, class_name, download_method, download_method.removesuffix("_download"),
        id=f"{module_path.removeprefix('juscraper.')}.{class_name}.{download_method}",
    )
    for module_path, class_name, download_method in _pares_download()
]


@pytest.mark.parametrize(
    ("module_path", "class_name", "download_method", "toplevel_method"),
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
