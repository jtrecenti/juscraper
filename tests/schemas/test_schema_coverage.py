"""Meta-teste: todo metodo publico nao-stub tem schema pydantic Input correspondente.

Varre ``juscraper.courts`` e ``juscraper.aggregators`` via reflexao e, para
cada metodo publico implementado (nao ``NotImplementedError``), confirma
que existe uma classe ``Input<Endpoint><Tribunal>`` mapeada em
``EXPECTED_SCHEMAS``.

A manutencao da lista e explicita de proposito: quando alguem adiciona um
tribunal novo ou implementa um endpoint que antes era stub, o teste falha
ate o mapping ser atualizado. Isso impede que schemas fiquem "orfaos"
silenciosamente.

Stubs (``raise NotImplementedError``) sao detectados automaticamente por
inspecao do source; nao precisam entrar em nenhuma lista.
"""
from __future__ import annotations

import importlib
import inspect
import pkgutil
from collections.abc import Iterator

from pydantic import BaseModel

PUBLIC_SEARCH_ENDPOINTS = ("cjsg", "cjpg")
PUBLIC_CONSULTA_ENDPOINTS = ("cpopg", "cposg")
# Endpoints especificos de um ou poucos tribunais (fora do quarteto canonico).
CUSTOM_ENDPOINTS = ("cjsg_ementa",)
ALL_PUBLIC_ENDPOINTS = (
    PUBLIC_SEARCH_ENDPOINTS + PUBLIC_CONSULTA_ENDPOINTS + CUSTOM_ENDPOINTS
)

# (tribunal_code_lowercase, endpoint_name) -> (module_path, class_name)
#
# eSAJ-puros (TJAC/TJAL/TJAM/TJCE/TJMS) compartilham ``InputCJSGEsajPuro`` em
# ``juscraper.courts._esaj.schemas`` porque a assinatura publica e identica.
# TJSP tem schema proprio porque a API diverge (``baixar_sg`` vs ``origem``).
EXPECTED_COURT_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    # Familia eSAJ-puros (wired, ja existe)
    ("tjac", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjal", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjam", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjce", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    ("tjms", "cjsg"): ("juscraper.courts._esaj.schemas", "InputCJSGEsajPuro"),
    # TJSP (wired, ja existe)
    ("tjsp", "cjsg"): ("juscraper.courts.tjsp.schemas", "InputCJSGTJSP"),
    ("tjsp", "cjpg"): ("juscraper.courts.tjsp.schemas", "InputCJPGTJSP"),
    ("tjsp", "cpopg"): ("juscraper.courts.tjsp.schemas", "InputCPOPGTJSP"),
    ("tjsp", "cposg"): ("juscraper.courts.tjsp.schemas", "InputCPOSGTJSP"),
    # Tribunais nao wired (schema-arquivo, documentacao executavel)
    ("tjap", "cjsg"): ("juscraper.courts.tjap.schemas", "InputCJSGTJAP"),
    ("tjba", "cjsg"): ("juscraper.courts.tjba.schemas", "InputCJSGTJBA"),
    ("tjdft", "cjsg"): ("juscraper.courts.tjdft.schemas", "InputCJSGTJDFT"),
    ("tjes", "cjsg"): ("juscraper.courts.tjes.schemas", "InputCJSGTJES"),
    ("tjes", "cjpg"): ("juscraper.courts.tjes.schemas", "InputCJPGTJES"),
    ("tjgo", "cjsg"): ("juscraper.courts.tjgo.schemas", "InputCJSGTJGO"),
    ("tjmg", "cjsg"): ("juscraper.courts.tjmg.schemas", "InputCJSGTJMG"),
    ("tjmt", "cjsg"): ("juscraper.courts.tjmt.schemas", "InputCJSGTJMT"),
    ("tjpa", "cjsg"): ("juscraper.courts.tjpa.schemas", "InputCJSGTJPA"),
    ("tjpb", "cjsg"): ("juscraper.courts.tjpb.schemas", "InputCJSGTJPB"),
    ("tjpe", "cjsg"): ("juscraper.courts.tjpe.schemas", "InputCJSGTJPE"),
    ("tjpi", "cjsg"): ("juscraper.courts.tjpi.schemas", "InputCJSGTJPI"),
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
    # PJe consulta pública (TRF3, TRF5) — wired via PJeConsultaScraper.INPUT_CPOPG.
    ("trf3", "cpopg"): ("juscraper.courts.trf3.schemas", "InputCpopgTRF3"),
    ("trf5", "cpopg"): ("juscraper.courts.trf5.schemas", "InputCpopgTRF5"),
    # eproc consulta pública (TRF6) — captcha-gated.
    ("trf6", "cpopg"): ("juscraper.courts.trf6.schemas", "InputCpopgTRF6"),
}

# Agregadores sao mapeados separadamente porque os endpoints fogem do
# padrao cjsg/cjpg/cpopg/cposg.
EXPECTED_AGGREGATOR_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    ("datajud", "listar_processos"): (
        "juscraper.aggregators.datajud.schemas",
        "InputListarProcessosDataJud",
    ),
    ("jusbr", "auth"): ("juscraper.aggregators.jusbr.schemas", "InputAuthJusBR"),
    ("jusbr", "auth_firefox"): (
        "juscraper.aggregators.jusbr.schemas",
        "InputAuthFirefoxJusBR",
    ),
    ("jusbr", "cpopg"): ("juscraper.aggregators.jusbr.schemas", "InputCPOPGJusBR"),
    ("jusbr", "download_documents"): (
        "juscraper.aggregators.jusbr.schemas",
        "InputDownloadDocumentsJusBR",
    ),
    ("comunica_cnj", "listar_comunicacoes"): (
        "juscraper.aggregators.comunica_cnj.schemas",
        "InputListarComunicacoesComunicaCNJ",
    ),
}


def _iter_court_scrapers() -> Iterator[tuple[str, type]]:
    import juscraper.courts as pkg

    for modinfo in pkgutil.iter_modules(pkg.__path__):
        if modinfo.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"juscraper.courts.{modinfo.name}.client")
        except ImportError:
            continue
        for name, obj in vars(mod).items():
            if (
                inspect.isclass(obj)
                and name.endswith("Scraper")
                and name != "BaseScraper"
                and obj.__module__ == mod.__name__
            ):
                yield modinfo.name, obj
                break


def _iter_aggregator_scrapers() -> Iterator[tuple[str, type]]:
    import juscraper.aggregators as pkg

    for modinfo in pkgutil.iter_modules(pkg.__path__):
        if modinfo.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"juscraper.aggregators.{modinfo.name}.client")
        except ImportError:
            continue
        for name, obj in vars(mod).items():
            if (
                inspect.isclass(obj)
                and name.endswith("Scraper")
                and obj.__module__ == mod.__name__
            ):
                yield modinfo.name, obj
                break


def _is_stub(method) -> bool:
    try:
        source = inspect.getsource(method)
    except (OSError, TypeError):
        return False
    return "raise NotImplementedError" in source


def _implemented_public_endpoints(cls: type, candidates) -> list[str]:
    found = []
    for endpoint in candidates:
        method = getattr(cls, endpoint, None)
        if method is None or not callable(method):
            continue
        if _is_stub(method):
            continue
        found.append(endpoint)
    return found


def _resolve(module_path: str, class_name: str) -> type[BaseModel] | None:
    try:
        mod = importlib.import_module(module_path)
    except ImportError:
        return None
    obj = getattr(mod, class_name, None)
    if obj is None or not inspect.isclass(obj) or not issubclass(obj, BaseModel):
        return None
    return obj


def test_every_court_endpoint_has_schema():
    missing: list[str] = []
    for tribunal, scraper_cls in _iter_court_scrapers():
        for endpoint in _implemented_public_endpoints(scraper_cls, ALL_PUBLIC_ENDPOINTS):
            key = (tribunal, endpoint)
            if key not in EXPECTED_COURT_SCHEMAS:
                missing.append(
                    f"{tribunal}.{endpoint}: nao mapeado em EXPECTED_COURT_SCHEMAS"
                )
                continue
            module_path, class_name = EXPECTED_COURT_SCHEMAS[key]
            resolved = _resolve(module_path, class_name)
            if resolved is None:
                missing.append(
                    f"{tribunal}.{endpoint}: {module_path}:{class_name} nao encontrado ou nao e BaseModel"
                )
    assert not missing, "Schemas faltando:\n" + "\n".join(missing)


def test_every_aggregator_endpoint_has_schema():
    candidates = (
        "auth",
        "auth_firefox",
        "cpopg",
        "download_documents",
        "listar_comunicacoes",
        "listar_processos",
    )
    missing: list[str] = []
    for name, scraper_cls in _iter_aggregator_scrapers():
        for endpoint in _implemented_public_endpoints(scraper_cls, candidates):
            key = (name, endpoint)
            if key not in EXPECTED_AGGREGATOR_SCHEMAS:
                missing.append(
                    f"{name}.{endpoint}: nao mapeado em EXPECTED_AGGREGATOR_SCHEMAS"
                )
                continue
            module_path, class_name = EXPECTED_AGGREGATOR_SCHEMAS[key]
            resolved = _resolve(module_path, class_name)
            if resolved is None:
                missing.append(
                    f"{name}.{endpoint}: {module_path}:{class_name} nao encontrado ou nao e BaseModel"
                )
    assert not missing, "Schemas faltando:\n" + "\n".join(missing)


def test_no_stale_entries_in_expected_mapping():
    """Impede que entradas sobrevivam depois que um endpoint vira stub ou o scraper some."""
    live_court = {
        (tribunal, endpoint)
        for tribunal, scraper_cls in _iter_court_scrapers()
        for endpoint in _implemented_public_endpoints(scraper_cls, ALL_PUBLIC_ENDPOINTS)
    }
    stale_court = set(EXPECTED_COURT_SCHEMAS) - live_court
    assert not stale_court, (
        "Entradas orfas em EXPECTED_COURT_SCHEMAS (remover):\n"
        + "\n".join(f"{t}.{e}" for t, e in sorted(stale_court))
    )

    aggregator_candidates = (
        "auth",
        "auth_firefox",
        "cpopg",
        "download_documents",
        "listar_comunicacoes",
        "listar_processos",
    )
    live_agg = {
        (name, endpoint)
        for name, scraper_cls in _iter_aggregator_scrapers()
        for endpoint in _implemented_public_endpoints(scraper_cls, aggregator_candidates)
    }
    stale_agg = set(EXPECTED_AGGREGATOR_SCHEMAS) - live_agg
    assert not stale_agg, (
        "Entradas orfas em EXPECTED_AGGREGATOR_SCHEMAS (remover):\n"
        + "\n".join(f"{n}.{e}" for n, e in sorted(stale_agg))
    )
