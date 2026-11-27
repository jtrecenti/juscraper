"""Paridade entre filtros listados na docstring e campos do schema pydantic.

O padrão de ``CONTRIBUTING.md > Docstrings de métodos públicos com kwargs``
exige correspondência entre filtros documentados e campos do schema.
``CASES`` cobre os métodos públicos com ``**kwargs``, e
``test_metodo_publico_com_kwargs_tem_paridade_registrada`` reprova o que
ficar fora dele sem motivo em ``SEM_PARIDADE``; ``DOWNLOAD_REFERENCE_CASES``
cobre os pares de download achados no pacote, que referenciam o principal via
``:meth:`` para evitar uma segunda lista de filtros sem validação de paridade.
"""
from __future__ import annotations

import importlib
import inspect
import json
import pkgutil
import re
import types
import typing
from datetime import date
from pathlib import Path
from typing import Any, Literal

import griffe
import pytest
from pydantic_core import PydanticUndefined

import juscraper
from juscraper import _SCRAPERS
from juscraper.utils.params import DATE_ALIAS_TO_CANONICAL, DATE_CANONICAL, SEARCH_ALIASES
from tests.schemas.test_signature_parity import _accepts_kwargs

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
    pytest.param(
        "juscraper.aggregators._pdpj_sso.mixin", "PdpjSsoMixin", "auth_govbr",
        "juscraper.aggregators.pdpj.schemas", "InputAuthGovbrPdpj",
        id="pdpj_sso.auth_govbr",
    ),
    pytest.param(
        "juscraper.aggregators.datajud.client", "DatajudScraper", "contar_processos",
        "juscraper.aggregators.datajud.schemas", "InputContarProcessosDataJud",
        id="datajud.contar_processos",
    ),
    pytest.param(
        "juscraper.aggregators.jusbr.client", "JusbrScraper", "auth",
        "juscraper.aggregators.jusbr.schemas", "InputAuthJusBR",
        id="jusbr.auth",
    ),
    pytest.param(
        "juscraper.aggregators.jusbr.client", "JusbrScraper", "cpopg",
        "juscraper.aggregators.jusbr.schemas", "InputCPOPGJusBR",
        id="jusbr.cpopg",
    ),
    pytest.param(
        "juscraper.aggregators.jusbr.client", "JusbrScraper", "download_documents",
        "juscraper.aggregators.jusbr.schemas", "InputDownloadDocumentsJusBR",
        id="jusbr.download_documents",
    ),
    pytest.param(
        "juscraper.courts._trf.base", "TRFConsultaScraper", "cpopg",
        "juscraper.courts._trf.schemas", "InputCpopgTRF",
        id="trf.cpopg",
    ),
    pytest.param(
        "juscraper.courts.stf.client", "STFScraper", "contar_decisoes",
        "juscraper.courts.stf.schemas", "InputContarDecisoesSTF",
        id="stf.contar_decisoes",
    ),
    pytest.param(
        "juscraper.courts.tjap.client", "TJAPScraper", "cjsg",
        "juscraper.courts.tjap.schemas", "InputCJSGTJAP",
        id="tjap.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjba.client", "TJBAScraper", "cjsg",
        "juscraper.courts.tjba.schemas", "InputCJSGTJBA",
        id="tjba.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjes.client", "TJESScraper", "cjsg",
        "juscraper.courts.tjes.schemas", "InputCJSGTJES",
        id="tjes.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjgo.client", "TJGOScraper", "cjsg",
        "juscraper.courts.tjgo.schemas", "InputCJSGTJGO",
        id="tjgo.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjmg.client", "TJMGScraper", "cjsg",
        "juscraper.courts.tjmg.schemas", "InputCJSGTJMG",
        id="tjmg.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjmt.client", "TJMTScraper", "cjsg",
        "juscraper.courts.tjmt.schemas", "InputCJSGTJMT",
        id="tjmt.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjpa.client", "TJPAScraper", "cjsg",
        "juscraper.courts.tjpa.schemas", "InputCJSGTJPA",
        id="tjpa.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjpb.client", "TJPBScraper", "cjsg",
        "juscraper.courts.tjpb.schemas", "InputCJSGTJPB",
        id="tjpb.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjpe.client", "TJPEScraper", "cjsg",
        "juscraper.courts.tjpe.schemas", "InputCJSGTJPE",
        id="tjpe.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjpi.client", "TJPIScraper", "cjsg",
        "juscraper.courts.tjpi.schemas", "InputCJSGTJPI",
        id="tjpi.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjpr.client", "TJPRScraper", "cjsg",
        "juscraper.courts.tjpr.schemas", "InputCJSGTJPR",
        id="tjpr.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjrn.client", "TJRNScraper", "cjsg",
        "juscraper.courts.tjrn.schemas", "InputCJSGTJRN",
        id="tjrn.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjro.client", "TJROScraper", "cjsg",
        "juscraper.courts.tjro.schemas", "InputCJSGTJRO",
        id="tjro.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjrr.client", "TJRRScraper", "cjsg",
        "juscraper.courts.tjrr.schemas", "InputCJSGTJRR",
        id="tjrr.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjrs.client", "TJRSScraper", "cjsg",
        "juscraper.courts.tjrs.schemas", "InputCJSGTJRS",
        id="tjrs.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjsc.client", "TJSCScraper", "cjsg",
        "juscraper.courts.tjsc.schemas", "InputCJSGTJSC",
        id="tjsc.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjto.client", "TJTOScraper", "cjsg",
        "juscraper.courts.tjto.schemas", "InputCJSGTJTO",
        id="tjto.cjsg",
    ),
    pytest.param(
        "juscraper.courts.tjes.client", "TJESScraper", "cjpg",
        "juscraper.courts.tjes.schemas", "InputCJPGTJES",
        id="tjes.cjpg",
    ),
    pytest.param(
        "juscraper.courts.tjto.client", "TJTOScraper", "cjpg",
        "juscraper.courts.tjto.schemas", "InputCJPGTJTO",
        id="tjto.cjpg",
    ),
    pytest.param(
        "juscraper.courts.tjpe.client", "TJPEScraper", "cpopg",
        "juscraper.courts._trf.schemas", "InputCpopgTRF",
        id="tjpe.cpopg",
    ),
    pytest.param(
        "juscraper.courts.tjmg.client", "TJMGScraper", "cposg",
        "juscraper.courts.tjmg.schemas", "InputCPOSGTJMG",
        id="tjmg.cposg",
    ),
    pytest.param(
        "juscraper.courts.trf3.client", "TRF3Scraper", "cpopg",
        "juscraper.courts.trf3.schemas", "InputCpopgTRF3",
        id="trf3.cpopg",
    ),
    pytest.param(
        "juscraper.courts.trf3.client", "TRF3Scraper", "cposg",
        "juscraper.courts.trf3.schemas", "InputCposgTRF3",
        id="trf3.cposg",
    ),
    pytest.param(
        "juscraper.courts.trf6.client", "TRF6Scraper", "cpopg",
        "juscraper.courts.trf6.schemas", "InputCpopgTRF6",
        id="trf6.cpopg",
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
    mod = importlib.import_module(module_path)
    klass = getattr(mod, class_name)
    return set(klass.model_fields.keys()) - EXPLICIT_PARAMS


def _args_documentados(method) -> set[str]:
    """Nomes das entradas de ``Args:``, lidos pelo parser Google do griffe, como faz o quartodoc."""
    doc = inspect.getdoc(method) or ""
    secoes = griffe.Docstring(doc, parser="google").parse()
    return {
        entrada.name.lstrip("*")
        for secao in secoes
        if isinstance(secao, griffe.DocstringSectionParameters)
        for entrada in secao.value
    }


def _parametros_explicitos(method) -> set[str]:
    return {
        nome
        for nome, parametro in inspect.signature(method).parameters.items()
        if nome != "self" and parametro.kind not in (parametro.VAR_POSITIONAL, parametro.VAR_KEYWORD)
    }


@pytest.mark.parametrize(
    "scraper_module,scraper_class,endpoint,schema_module,schema_class",
    CASES,
)
def test_docstring_lists_schema_fields(
    scraper_module, scraper_class, endpoint, schema_module, schema_class,
):
    """Cada campo do schema está documentado: em ``Args:``, se é parâmetro da assinatura, ou em ``**kwargs``."""
    mod = importlib.import_module(scraper_module)
    method = getattr(getattr(mod, scraper_class), endpoint)

    explicitos = _parametros_explicitos(method)
    todos = set(getattr(importlib.import_module(schema_module), schema_class).model_fields)
    fields = _schema_filter_fields(schema_module, schema_class) - explicitos
    # Um nome em ``DEPRECATED_ALIASES`` so e subtraido quando NAO e um campo
    # real do schema do caso atual. Cobre colisoes onde o mesmo nome e
    # alias deprecado em outros tribunais (``query`` -> ``pesquisa``) mas
    # campo real aqui (``query`` no DataJud e o override Elasticsearch).
    bullets = set(_docstring_bullets(method)) - EXPLICIT_PARAMS - (DEPRECATED_ALIASES - fields)

    schema_only = fields - bullets
    docstring_only = bullets - fields
    sem_args = (todos & explicitos) - _args_documentados(method)

    assert not schema_only and not docstring_only and not sem_args, (
        f"{scraper_class}.{endpoint} — paridade docstring/schema falhou:\n"
        f"  campos no schema {schema_class} mas nao na docstring: "
        f"{sorted(schema_only) or '-'}\n"
        f"  bullets na docstring mas nao no schema: "
        f"{sorted(docstring_only) or '-'}\n"
        f"  parametros da assinatura, campos do schema, sem entrada em Args: "
        f"{sorted(sem_args) or '-'}\n"
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
    "scraper_module,scraper_class,endpoint,schema_module,schema_class",
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
    klass = getattr(schema_mod, schema_class)

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
    for info in pkgutil.walk_packages(juscraper.__path__, "juscraper."):
        mod = importlib.import_module(info.name)
        for class_name, klass in vars(mod).items():
            if not inspect.isclass(klass) or klass.__module__ != mod.__name__:
                continue
            for name, attr in vars(klass).items():
                if name.startswith("_") or not name.endswith("_download") or not callable(attr):
                    continue
                principal = getattr(klass, name.removesuffix("_download"), None)
                if principal is not None and _accepts_kwargs(principal):
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


#: Método público com ``**kwargs`` que fica fora de ``CASES``, com o motivo.
#: Só entra aqui o que não tem filtros a conferir contra um schema.
SEM_PARIDADE: dict[tuple[str, str, str], str] = {
    ("juscraper.courts.tse.client", "TSEScraper", "cjsg"): (
        "stub: ``*args``/``**kwargs`` só existem para levantar NotImplementedError; não há schema"
    ),
    ("juscraper.courts.trf3.client", "TRF3Scraper", "cpopg_parse"): (
        "``**kwargs`` só recebe o alias deprecado ``htmls`` (-> ``brutos``); não há filtros nem schema"
    ),
}


def _metodos_com_kwargs() -> set[tuple[str, str, str]]:
    """Métodos públicos com ``**kwargs`` da hierarquia de cada raspador registrado.

    Devolve ``(módulo, classe, método)`` pela classe que define o método, como
    ``CASES`` registra: o herdado conta uma vez, na classe base ou no mixin.
    Os ``*_download`` ficam com :func:`test_download_docstring_references_toplevel`.
    """
    metodos = set()
    for caminho in _SCRAPERS.values():
        modulo, nome = caminho.split(":")
        raspador = getattr(importlib.import_module(modulo), nome)
        for classe in raspador.__mro__[:-1]:
            for nome_metodo, atributo in vars(classe).items():
                if nome_metodo.startswith("_") or nome_metodo.endswith("_download") or not callable(atributo):
                    continue
                if _accepts_kwargs(atributo):
                    metodos.add((classe.__module__, classe.__qualname__, nome_metodo))
    return metodos


def test_metodo_publico_com_kwargs_tem_paridade_registrada():
    """Todo método público com ``**kwargs`` está em ``CASES`` ou em ``SEM_PARIDADE``.

    Sem isso, um endpoint novo, ou um existente esquecido, fica com a lista de
    filtros da docstring livre para divergir do schema.
    """
    registrados = {tuple(p.values[:3]) for p in CASES}
    achados = _metodos_com_kwargs()
    faltam = achados - registrados - set(SEM_PARIDADE)
    sobram = set(SEM_PARIDADE) - achados
    assert not faltam and not sobram, (
        "Métodos públicos com **kwargs sem paridade registrada (incluir em CASES, "
        "com o schema, ou em SEM_PARIDADE, com o motivo):\n"
        + "".join(f"  {'.'.join(m)}\n" for m in sorted(faltam))
        + ("Entradas de SEM_PARIDADE que não existem mais:\n" if sobram else "")
        + "".join(f"  {'.'.join(m)}\n" for m in sorted(sobram))
    )


def _aliases_aceitos(method, schema) -> set[str]:
    """Aliases que o pipeline de entrada consome para os campos deste endpoint.

    ``query``/``termo`` quando há ``pesquisa``; o alias de data cujo nome
    canônico é campo do schema ou parâmetro da assinatura (``DATE_ALIAS_TO_CANONICAL``).
    """
    nomes = set(schema.model_fields) | _parametros_explicitos(method)
    aceitos = {a for a, canonico in DATE_ALIAS_TO_CANONICAL.items() if canonico in nomes}
    if "pesquisa" in nomes:
        aceitos |= set(SEARCH_ALIASES)
    return aceitos


#: Endpoint que não consome um alias que :func:`_aliases_aceitos` presume, com o motivo.
ALIASES_NAO_CONSUMIDOS: dict[tuple[str, str], tuple[frozenset[str], str]] = {
    ("ComunicaCNJScraper", "listar_comunicacoes"): (
        frozenset(SEARCH_ALIASES),
        "chama ``normalize_paginas``, não ``normalize_pesquisa``: ``query``/``termo`` são kwargs desconhecidos",
    ),
}


@pytest.mark.parametrize(
    "scraper_module,scraper_class,endpoint,schema_module,schema_class",
    CASES,
)
def test_docstring_cita_aliases_aceitos(
    scraper_module, scraper_class, endpoint, schema_module, schema_class,
):
    """Cada alias deprecado que o endpoint consome aparece na docstring, pelo nome inteiro."""
    mod = importlib.import_module(scraper_module)
    method = getattr(getattr(mod, scraper_class), endpoint)
    schema = getattr(importlib.import_module(schema_module), schema_class)
    excluidos = ALIASES_NAO_CONSUMIDOS.get((scraper_class, endpoint), (frozenset(), ""))[0]
    citados = set(_NAME_RE.findall(inspect.getdoc(method) or ""))
    faltam = _aliases_aceitos(method, schema) - excluidos - citados
    assert not faltam, (
        f"{scraper_class}.{endpoint} aceita, com DeprecationWarning, aliases que a "
        f"docstring não cita: {sorted(faltam)}.\n"
        "Listar em 'Aliases deprecados:' pelo nome inteiro (``data_julgamento_ate``, "
        "não ``_ate``). Endpoint que não consome o alias entra em ALIASES_NAO_CONSUMIDOS."
    )
