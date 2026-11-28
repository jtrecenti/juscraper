"""Registro dos schemas pydantic e dos raspadores, compartilhado por ``tests/schemas``.

Os mapas ``EXPECTED_*`` ligam cada endpoint publico ``(sigla, endpoint)`` ao seu
schema ``Input*`` ou ``Output*``. A manutencao e explicita de proposito:
:mod:`tests.schemas.test_schema_coverage` reprova endpoint implementado sem
entrada e entrada sem endpoint, e os demais testes de ``tests/schemas`` derivam
os casos daqui.

Tudo aqui falha alto: raspador que nao importa, schema que nao resolve e entrada
sem raspador levantam com o erro original, em vez de sumir dos testes.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Callable, Iterator
from datetime import date
from functools import cache
from types import ModuleType
from typing import Any, NamedTuple, get_args

import pandas as pd
from pydantic import BaseModel

import juscraper
import juscraper.aggregators
import juscraper.courts
from juscraper.utils.params import DATE_ALIASES, SEARCH_ALIASES

# Os metodos ``listar_classes``/``listar_assuntos``/``listar_orgaos``/
# ``listar_varas`` da familia eSAJ (refs #228) ficam fora deste regime de
# proposito: nao recebem input de usuario (so ``grau``, um literal), entao um
# ``Input*`` com ``extra="forbid"`` seria cerimonia sem valor de validacao.
COURT_ENDPOINTS = (
    "cjsg", "cjpg", "cpopg", "cposg", "cjsg_ementa", "listar_decisoes", "contar_decisoes",
)
AGGREGATOR_ENDPOINTS = (
    "auth",
    "auth_firefox",
    "auth_govbr",
    "contar",
    "contar_processos",
    "cpopg",
    "download_documents",
    "listar_comunicacoes",
    "listar_decisoes",
    "listar_processos",
    "pesquisa",
)

#: Aliases deprecados de busca e data, resolvidos antes do pydantic.
ALIASES_DEPRECADOS = frozenset(SEARCH_ALIASES) | frozenset(DATE_ALIASES)

# (tribunal_code_lowercase, endpoint_name) -> (module_path, class_name)
#
# eSAJ-puros (TJAC/TJAL/TJAM/TJCE/TJMS) compartilham ``InputCJSGEsajPuro`` em
# ``juscraper.courts._esaj.schemas`` porque a assinatura publica e identica.
# TJSP tem schema proprio porque a API diverge (``baixar_sg`` vs ``origem``).
EXPECTED_COURT_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    # Familia eSAJ-puros
    ("tjac", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjal", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjam", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjce", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjms", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    # TJSP
    ("tjsp", "cjsg"): ("juscraper.courts.tjsp.schemas", "InputCJSGTJSP"),
    ("tjsp", "cjpg"): ("juscraper.courts._esaj.schemas", "InputCJPGEsaj"),
    ("tjsp", "cpopg"): ("juscraper.courts.tjsp.schemas", "InputCPOPGTJSP"),
    ("tjsp", "cposg"): ("juscraper.courts.tjsp.schemas", "InputCPOSGTJSP"),
    # TJMS herda o cjpg do TJSP (``_esaj/cjpg.py``), com o mesmo schema (#487).
    ("tjms", "cjpg"): ("juscraper.courts._esaj.schemas", "InputCJPGEsaj"),
    # Demais tribunais
    ("tjap", "cjsg"): ("juscraper.courts.tjap.schemas", "InputCJSGTJAP"),
    ("tjba", "cjsg"): ("juscraper.courts.tjba.schemas", "InputCJSGTJBA"),
    ("tjdft", "cjsg"): ("juscraper.courts.tjdft.schemas", "InputCJSGTJDFT"),
    ("tjes", "cjsg"): ("juscraper.courts.tjes.schemas", "InputCJSGTJES"),
    ("tjes", "cjpg"): ("juscraper.courts.tjes.schemas", "InputCJPGTJES"),
    ("tjgo", "cjsg"): ("juscraper.courts.tjgo.schemas", "InputCJSGTJGO"),
    ("tjmg", "cjsg"): ("juscraper.courts.tjmg.schemas", "InputCJSGTJMG"),
    ("tjmg", "cposg"): ("juscraper.courts.tjmg.schemas", "InputCPOSGTJMG"),
    ("tjmt", "cjsg"): ("juscraper.courts.tjmt.schemas", "InputCJSGTJMT"),
    ("tjpa", "cjsg"): ("juscraper.courts.tjpa.schemas", "InputCJSGTJPA"),
    ("tjpb", "cjsg"): ("juscraper.courts.tjpb.schemas", "InputCJSGTJPB"),
    ("tjpe", "cjsg"): ("juscraper.courts.tjpe.schemas", "InputCJSGTJPE"),
    ("tjpi", "cjsg"): ("juscraper.courts.tjpi.schemas", "InputCJSGTJPI"),
    ("stm", "cjsg"): ("juscraper.courts.stm.schemas", "InputCJSGSTM"),
    ("tjpr", "cjsg"): ("juscraper.courts.tjpr.schemas", "InputCJSGTJPR"),
    ("tjrj", "cjsg"): ("juscraper.courts.tjrj.schemas", "InputCJSGTJRJ"),
    ("tjrn", "cjsg"): ("juscraper.courts.tjrn.schemas", "InputCJSGTJRN"),
    ("tjro", "cjsg"): ("juscraper.courts.tjro.schemas", "InputCJSGTJRO"),
    ("tjrr", "cjsg"): ("juscraper.courts.tjrr.schemas", "InputCJSGTJRR"),
    ("tjrs", "cjsg"): ("juscraper.courts.tjrs.schemas", "InputCJSGTJRS"),
    ("tjsc", "cjsg"): ("juscraper.courts.tjsc.schemas", "InputCJSGTJSC"),
    ("tjto", "cjsg"): ("juscraper.courts.tjto.schemas", "InputCJSGTJTO"),
    ("tjto", "cjpg"): ("juscraper.courts.tjto.schemas", "InputCJPGTJTO"),
    ("tjto", "cjsg_ementa"): (
        "juscraper.courts.tjto.schemas",
        "InputCjsgEmentaTJTO",
    ),
    # PJe consulta pública JSF (TRF1, TRF5): schema compartilhado da
    # família ``_trf`` (assinatura pública idêntica nos dois).
    ("trf1", "cpopg"): ("juscraper.courts._trf.schemas", "InputCpopgTRF"),
    ("trf5", "cpopg"): ("juscraper.courts._trf.schemas", "InputCpopgTRF"),
    # TRF3: consulta pública do PJe pela API JSON, fora da família ``_trf``.
    ("trf3", "cpopg"): ("juscraper.courts.trf3.schemas", "InputCpopgTRF3"),
    ("trf3", "cposg"): ("juscraper.courts.trf3.schemas", "InputCposgTRF3"),
    # Busca de jurisprudência do TRF3 (portal próprio, fora do PJe).
    ("trf3", "cjsg"): ("juscraper.courts.trf3.cjsg_schemas", "InputCJSGTRF3"),
    # TJPE 1º grau roda o mesmo PJe ConsultaPública dos TRFs.
    ("tjpe", "cpopg"): ("juscraper.courts._trf.schemas", "InputCpopgTRF"),
    # eproc consulta pública (TRF6) — captcha-gated.
    ("trf6", "cpopg"): ("juscraper.courts.trf6.schemas", "InputCpopgTRF6"),
    # Busca de jurisprudencia do STF (acordaos e monocraticas).
    ("stf", "listar_decisoes"): ("juscraper.courts.stf.schemas", "InputListarDecisoesSTF"),
    ("stf", "contar_decisoes"): ("juscraper.courts.stf.schemas", "InputContarDecisoesSTF"),
}

# Agregadores sao mapeados separadamente porque os endpoints fogem do
# padrao cjsg/cjpg/cpopg/cposg.
EXPECTED_AGGREGATOR_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    ("datajud", "listar_processos"): (
        "juscraper.aggregators.datajud.schemas",
        "InputListarProcessosDataJud",
    ),
    ("datajud", "contar_processos"): (
        "juscraper.aggregators.datajud.schemas",
        "InputContarProcessosDataJud",
    ),
    ("jusbr", "auth"): ("juscraper.aggregators.jusbr.schemas", "InputAuthJusBR"),
    ("jusbr", "auth_firefox"): (
        "juscraper.aggregators.jusbr.schemas",
        "InputAuthFirefoxJusBR",
    ),
    ("jusbr", "auth_govbr"): ("juscraper.aggregators.jusbr.schemas", "InputAuthGovbrJusBR"),
    ("jusbr", "cpopg"): ("juscraper.aggregators.jusbr.schemas", "InputCPOPGJusBR"),
    ("jusbr", "download_documents"): (
        "juscraper.aggregators.jusbr.schemas",
        "InputDownloadDocumentsJusBR",
    ),
    ("comunica_cnj", "listar_comunicacoes"): (
        "juscraper.aggregators.comunica_cnj.schemas",
        "InputListarComunicacoesComunicaCNJ",
    ),
    ("falcao", "listar_decisoes"): ("juscraper.aggregators.falcao.schemas", "InputListarDecisoesFalcao"),
    ("pdpj", "auth"): ("juscraper.aggregators.pdpj.schemas", "InputAuthPdpj"),
    ("pdpj", "auth_govbr"): ("juscraper.aggregators.pdpj.schemas", "InputAuthGovbrPdpj"),
    ("pdpj", "cpopg"): ("juscraper.aggregators.pdpj.schemas", "InputCnjPdpj"),
    ("pdpj", "pesquisa"): ("juscraper.aggregators.pdpj.schemas", "InputPesquisaPdpj"),
    ("pdpj", "contar"): ("juscraper.aggregators.pdpj.schemas", "InputContarPdpj"),
    ("pdpj", "download_documents"): (
        "juscraper.aggregators.pdpj.schemas",
        "InputDownloadDocumentsPdpj",
    ),
}

# (sigla, endpoint) -> (modulo, classe) do Output; paralelo aos mapas de Input.
EXPECTED_COURT_OUTPUT_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    # eSAJ-puros compartilham Output — parser dinamico, marcar skip.
    ("tjac", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjal", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjam", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjce", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjms", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjsp", "cjsg"): ("juscraper.courts.tjsp.schemas", "OutputCJSGTJSP"),
    ("tjsp", "cjpg"): ("juscraper.courts._esaj.schemas", "OutputCJPGEsaj"),
    ("tjsp", "cpopg"): ("juscraper.courts.tjsp.schemas", "OutputCPOPGTJSP"),
    ("tjsp", "cposg"): ("juscraper.courts.tjsp.schemas", "OutputCPOSGTJSP"),
    ("tjms", "cjpg"): ("juscraper.courts._esaj.schemas", "OutputCJPGEsaj"),
    ("tjap", "cjsg"): ("juscraper.courts.tjap.schemas", "OutputCJSGTJAP"),
    ("tjba", "cjsg"): ("juscraper.courts.tjba.schemas", "OutputCJSGTJBA"),
    ("tjdft", "cjsg"): ("juscraper.courts.tjdft.schemas", "OutputCJSGTJDFT"),
    ("tjes", "cjsg"): ("juscraper.courts.tjes.schemas", "OutputCJSGTJES"),
    ("tjes", "cjpg"): ("juscraper.courts.tjes.schemas", "OutputCJPGTJES"),
    ("tjgo", "cjsg"): ("juscraper.courts.tjgo.schemas", "OutputCJSGTJGO"),
    ("tjmg", "cjsg"): ("juscraper.courts.tjmg.schemas", "OutputCJSGTJMG"),
    ("tjmg", "cposg"): ("juscraper.courts.tjmg.schemas", "OutputCPOSGTJMG"),
    ("tjmt", "cjsg"): ("juscraper.courts.tjmt.schemas", "OutputCJSGTJMT"),
    ("tjpa", "cjsg"): ("juscraper.courts.tjpa.schemas", "OutputCJSGTJPA"),
    ("tjpb", "cjsg"): ("juscraper.courts.tjpb.schemas", "OutputCJSGTJPB"),
    ("tjpe", "cjsg"): ("juscraper.courts.tjpe.schemas", "OutputCJSGTJPE"),
    ("tjpi", "cjsg"): ("juscraper.courts.tjpi.schemas", "OutputCJSGTJPI"),
    ("stm", "cjsg"): ("juscraper.courts.stm.schemas", "OutputCJSGSTM"),
    ("tjpr", "cjsg"): ("juscraper.courts.tjpr.schemas", "OutputCJSGTJPR"),
    ("tjrj", "cjsg"): ("juscraper.courts.tjrj.schemas", "OutputCJSGTJRJ"),
    ("tjrn", "cjsg"): ("juscraper.courts.tjrn.schemas", "OutputCJSGTJRN"),
    ("tjro", "cjsg"): ("juscraper.courts.tjro.schemas", "OutputCJSGTJRO"),
    ("tjrr", "cjsg"): ("juscraper.courts.tjrr.schemas", "OutputCJSGTJRR"),
    ("tjrs", "cjsg"): ("juscraper.courts.tjrs.schemas", "OutputCJSGTJRS"),
    ("tjsc", "cjsg"): ("juscraper.courts.tjsc.schemas", "OutputCJSGTJSC"),
    ("tjto", "cjsg"): ("juscraper.courts.tjto.schemas", "OutputCJSGTJTO"),
    ("tjto", "cjpg"): ("juscraper.courts.tjto.schemas", "OutputCJPGTJTO"),
    ("trf1", "cpopg"): ("juscraper.courts._trf.schemas", "OutputCpopgTRF"),
    ("trf3", "cpopg"): ("juscraper.courts.trf3.schemas", "OutputCpopgTRF3"),
    ("trf3", "cposg"): ("juscraper.courts.trf3.schemas", "OutputCposgTRF3"),
    ("trf3", "cjsg"): ("juscraper.courts.trf3.cjsg_schemas", "OutputCJSGTRF3"),
    ("trf5", "cpopg"): ("juscraper.courts._trf.schemas", "OutputCpopgTRF"),
    # TJPE 1º grau roda o mesmo PJe ConsultaPública dos TRFs.
    ("tjpe", "cpopg"): ("juscraper.courts._trf.schemas", "OutputCpopgTRF"),
    ("trf6", "cpopg"): ("juscraper.courts.trf6.schemas", "OutputCpopgTRF6"),
    ("stf", "listar_decisoes"): ("juscraper.courts.stf.schemas", "OutputListarDecisoesSTF"),
    ("stf", "contar_decisoes"): ("juscraper.courts.stf.schemas", "OutputContarDecisoesSTF"),
}

EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    ("datajud", "listar_processos"): (
        "juscraper.aggregators.datajud.schemas",
        "OutputListarProcessosDataJud",
    ),
    ("jusbr", "cpopg"): ("juscraper.aggregators.jusbr.schemas", "OutputCPOPGJusBR"),
    ("jusbr", "download_documents"): (
        "juscraper.aggregators.jusbr.schemas",
        "OutputDownloadDocumentsJusBR",
    ),
    ("comunica_cnj", "listar_comunicacoes"): (
        "juscraper.aggregators.comunica_cnj.schemas",
        "OutputListarComunicacoesComunicaCNJ",
    ),
    ("falcao", "listar_decisoes"): ("juscraper.aggregators.falcao.schemas", "OutputListarDecisoesFalcao"),
    ("pdpj", "cpopg"): ("juscraper.aggregators.pdpj.schemas", "OutputCpopgPdpj"),
    ("pdpj", "pesquisa"): ("juscraper.aggregators.pdpj.schemas", "OutputPesquisaPdpj"),
    ("datajud", "contar_processos"): ("juscraper.aggregators.datajud.schemas", "OutputContarProcessosDataJud"),
    ("pdpj", "download_documents"): ("juscraper.aggregators.pdpj.schemas", "OutputDownloadDocumentsPdpj"),
}

#: Mapas de tribunais e agregadores juntos. As siglas nao se repetem:
#: :func:`raspadores` reprova sigla de tribunal igual a de agregador.
INPUT_SCHEMAS = {**EXPECTED_COURT_SCHEMAS, **EXPECTED_AGGREGATOR_SCHEMAS}
OUTPUT_SCHEMAS = {**EXPECTED_COURT_OUTPUT_SCHEMAS, **EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS}


def _raspadores(pacote: ModuleType) -> dict[str, type]:
    """Sigla -> classe ``*Scraper`` do ``client.py`` de cada subpacote publico."""
    out: dict[str, type] = {}
    for modinfo in pkgutil.iter_modules(pacote.__path__):
        if modinfo.name.startswith("_") or not modinfo.ispkg:
            continue
        mod = importlib.import_module(f"{pacote.__name__}.{modinfo.name}.client")
        classes = [
            obj
            for name, obj in vars(mod).items()
            if inspect.isclass(obj) and name.endswith("Scraper") and obj.__module__ == mod.__name__
        ]
        assert len(classes) == 1, f"{mod.__name__} define {len(classes)} classes *Scraper, e nao uma"
        out[modinfo.name] = classes[0]
    return out


@cache
def raspadores_tribunais() -> dict[str, type]:
    return _raspadores(juscraper.courts)


@cache
def raspadores_agregadores() -> dict[str, type]:
    return _raspadores(juscraper.aggregators)


def raspadores() -> dict[str, type]:
    tribunais, agregadores = raspadores_tribunais(), raspadores_agregadores()
    repetidas = tribunais.keys() & agregadores.keys()
    assert not repetidas, f"Siglas de tribunal e de agregador repetidas: {sorted(repetidas)}"
    return {**tribunais, **agregadores}


def resolve(modulo: str, classe: str) -> type[BaseModel]:
    """Classe pydantic ``modulo:classe``; levanta se o modulo ou a classe faltar."""
    obj = getattr(importlib.import_module(modulo), classe)
    assert inspect.isclass(obj), f"{modulo}:{classe} nao e classe"
    assert issubclass(obj, BaseModel), f"{modulo}:{classe} nao e BaseModel"
    return obj


def is_stub(metodo: Callable[..., object]) -> bool:
    try:
        source = inspect.getsource(metodo)
    except (OSError, TypeError):
        return False
    return "raise NotImplementedError" in source


def endpoints_implementados(cls: type, candidatos: tuple[str, ...]) -> list[str]:
    """Candidatos que ``cls`` implementa (metodo existente e nao stub)."""
    return [
        endpoint
        for endpoint in candidatos
        if callable(metodo := getattr(cls, endpoint, None)) and not is_stub(metodo)
    ]


class SchemaMapeado(NamedTuple):
    """Entrada de um mapa ``EXPECTED_*`` com a classe do raspador."""

    sigla: str
    endpoint: str
    raspador: type
    modulo: str
    classe: str

    @property
    def schema(self) -> type[BaseModel]:
        return resolve(self.modulo, self.classe)

    @property
    def id(self) -> str:
        return f"{self.sigla}.{self.endpoint}"


def schemas_mapeados(mapa: dict[tuple[str, str], tuple[str, str]] = INPUT_SCHEMAS) -> list[SchemaMapeado]:
    """Casa cada entrada de ``mapa`` com a classe do raspador da sigla.

    Entrada sem raspador e erro do mapa: reprova a coleta.
    """
    todos = raspadores()
    sem_raspador = sorted({sigla for sigla, _ in mapa} - todos.keys())
    assert not sem_raspador, f"Entradas do mapa sem raspador: {sem_raspador}"
    return [
        SchemaMapeado(sigla, endpoint, todos[sigla], modulo, classe)
        for (sigla, endpoint), (modulo, classe) in mapa.items()
    ]


def modulos(sufixo: str | None = None) -> Iterator[ModuleType]:
    """Modulos de ``juscraper``, em ordem alfabetica por nivel.

    Com ``sufixo``, so os que tem um trecho do nome terminado nele: o proprio
    modulo (``cjsg_schemas.py``) ou um pacote que o contem (``juscraper.schemas.cjsg``).
    """
    for modinfo in pkgutil.walk_packages(juscraper.__path__, "juscraper."):
        if sufixo is None or any(parte.endswith(sufixo) for parte in modinfo.name.split(".")[1:]):
            yield importlib.import_module(modinfo.name)


def modulos_de_schemas() -> Iterator[ModuleType]:
    """Todo modulo de schemas (``schemas.py``, ``cjsg_schemas.py``, pacote ``schemas`` e seus submodulos)."""
    return modulos("schemas")


def schemas_definidos() -> list[type[BaseModel]]:
    """Todo modelo pydantic definido (nao so importado) num modulo de schemas, em ordem estavel."""
    return [
        obj
        for mod in modulos_de_schemas()
        for obj in vars(mod).values()
        if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == mod.__name__
    ]


def parametros_explicitos(metodo: Callable[..., object]) -> set[str]:
    """Parametros nomeados da assinatura, sem ``*args``/``**kwargs``."""
    return {
        nome
        for nome, param in inspect.signature(metodo).parameters.items()
        if param.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    }


def aceita_kwargs(metodo: Callable[..., object]) -> bool:
    return any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in inspect.signature(metodo).parameters.values()
    )


#: Valores de campos obrigatorios que precisam de formato proprio.
_CNJ = "1000000-00.2024.8.26.0100"
_VALORES_POR_NOME: dict[str, Any] = {
    "pesquisa": "termo",
    "token": "tok",
    "uuid": "abc-123",
    "ementa": "Texto da ementa.",
    "id_processo": "1000",
    **dict.fromkeys(("id_cnj", "processo", "numeroProcesso", "processo_pesquisado", "numero_processo"), _CNJ),
}


def _valor_neutro(anotacao: object) -> Any:
    tipos = get_args(anotacao) or (anotacao,)
    for tipo, valor in ((pd.DataFrame, pd.DataFrame()), (int, 0), (float, 0.0), (date, date(2024, 1, 1))):
        if tipo in tipos and str not in tipos:
            return valor
    return "x"


def payload_minimo(schema: type[BaseModel]) -> dict[str, Any]:
    """Valores neutros para os campos obrigatorios de ``schema`` (Input ou Output)."""
    return {
        nome: _VALORES_POR_NOME[nome] if nome in _VALORES_POR_NOME else _valor_neutro(info.annotation)
        for nome, info in schema.model_fields.items()
        if info.is_required()
    }
