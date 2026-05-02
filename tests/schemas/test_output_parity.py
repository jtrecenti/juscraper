"""Paridade entre campos declarados no Output schema e chaves do parser.

Para cada par ``(tribunal, endpoint)`` mapeado em
:data:`EXPECTED_COURT_SCHEMAS_OUTPUTS` / :data:`EXPECTED_AGGREGATOR_SCHEMAS_OUTPUTS`,
o teste carrega o **source do modulo de parser** e verifica que todo
campo nao-herdado declarado no Output aparece como string literal no
parser — ``"campo"`` ou ``'campo'``. Busca por substring (nao AST) e
deliberada: pega chaves em dicts literais, listas de whitelist (ex.
``_MAIN_FIELDS``), dicts de rename (ex. ``_FIELD_RENAMES``) e docstrings
que mencionam colunas — tudo que indica que o parser "fala" daquele
campo.

Campos herdados de :class:`OutputCJSGBase` (``processo``, ``ementa``,
``data_julgamento``) sao contratos universais e nao precisam aparecer no
parser concreto (muitos parsers os entregam sem nome explicito via
``rows.append({"processo": ...})``; a conferencia acima ja cobre isso).

Parsers dinamicos que extraem rotulos de HTML sem dict literal
(eSAJ puro) sao ``skip`` — o Output ja foi validado manualmente contra
o parser compartilhado em ``_esaj/parse.py``.
"""
from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable

import pytest
from pydantic import BaseModel

from tests.schemas.test_schema_coverage import _iter_aggregator_scrapers, _iter_court_scrapers

# Mapping (tribunal, endpoint) -> (module_with_output, output_class_name).
# Paralelo ao EXPECTED_COURT_SCHEMAS do test_schema_coverage, mas para
# Outputs (o outro mapa cuida de Inputs).
EXPECTED_COURT_OUTPUT_SCHEMAS: dict[tuple[str, str], tuple[str, str]] = {
    # eSAJ-puros compartilham Output — parser dinamico, marcar skip.
    ("tjac", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjal", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjam", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjce", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjms", "cjsg"): ("juscraper.courts._esaj.schemas", "OutputCJSGEsaj"),
    ("tjsp", "cjsg"): ("juscraper.courts.tjsp.schemas", "OutputCJSGTJSP"),
    ("tjsp", "cjpg"): ("juscraper.courts.tjsp.schemas", "OutputCJPGTJSP"),
    ("tjsp", "cpopg"): ("juscraper.courts.tjsp.schemas", "OutputCPOPGTJSP"),
    ("tjsp", "cposg"): ("juscraper.courts.tjsp.schemas", "OutputCPOSGTJSP"),
    ("tjap", "cjsg"): ("juscraper.courts.tjap.schemas", "OutputCJSGTJAP"),
    ("tjba", "cjsg"): ("juscraper.courts.tjba.schemas", "OutputCJSGTJBA"),
    ("tjdft", "cjsg"): ("juscraper.courts.tjdft.schemas", "OutputCJSGTJDFT"),
    ("tjes", "cjsg"): ("juscraper.courts.tjes.schemas", "OutputCJSGTJES"),
    ("tjes", "cjpg"): ("juscraper.courts.tjes.schemas", "OutputCJPGTJES"),
    ("tjgo", "cjsg"): ("juscraper.courts.tjgo.schemas", "OutputCJSGTJGO"),
    ("tjmg", "cjsg"): ("juscraper.courts.tjmg.schemas", "OutputCJSGTJMG"),
    ("tjmt", "cjsg"): ("juscraper.courts.tjmt.schemas", "OutputCJSGTJMT"),
    ("tjpa", "cjsg"): ("juscraper.courts.tjpa.schemas", "OutputCJSGTJPA"),
    ("tjpb", "cjsg"): ("juscraper.courts.tjpb.schemas", "OutputCJSGTJPB"),
    ("tjpe", "cjsg"): ("juscraper.courts.tjpe.schemas", "OutputCJSGTJPE"),
    ("tjpi", "cjsg"): ("juscraper.courts.tjpi.schemas", "OutputCJSGTJPI"),
    ("tjpr", "cjsg"): ("juscraper.courts.tjpr.schemas", "OutputCJSGTJPR"),
    ("tjrj", "cjsg"): ("juscraper.courts.tjrj.schemas", "OutputCJSGTJRJ"),
    ("tjrn", "cjsg"): ("juscraper.courts.tjrn.schemas", "OutputCJSGTJRN"),
    ("tjro", "cjsg"): ("juscraper.courts.tjro.schemas", "OutputCJSGTJRO"),
    ("tjrr", "cjsg"): ("juscraper.courts.tjrr.schemas", "OutputCJSGTJRR"),
    ("tjrs", "cjsg"): ("juscraper.courts.tjrs.schemas", "OutputCJSGTJRS"),
    ("tjsc", "cjsg"): ("juscraper.courts.tjsc.schemas", "OutputCJSGTJSC"),
    ("tjto", "cjsg"): ("juscraper.courts.tjto.schemas", "OutputCJSGTJTO"),
    ("tjto", "cjpg"): ("juscraper.courts.tjto.schemas", "OutputCJPGTJTO"),
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
}

# Campos que herdamos de OutputCJSGBase / OutputCnjConsultaBase e nao
# precisamos verificar no parser concreto (contratos de base).
BASE_FIELDS_CJSG = frozenset({"processo", "ementa", "data_julgamento"})
BASE_FIELDS_CONSULTA = frozenset({"id_cnj"})

# Casos em que o parser e dinamico (label-based) ou passthrough — nao da
# para detectar campos por substring no source. Marcar skip com motivo.
SKIP_REASONS: dict[tuple[str, str], str] = {
    # eSAJ puro: parser extrai rotulos do HTML, nao tem dict literal.
    # Validado manualmente em _esaj/parse.py:_parse_single_page.
    ("tjac", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGEsaj validado manualmente",
    ("tjal", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGEsaj validado manualmente",
    ("tjam", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGEsaj validado manualmente",
    ("tjce", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGEsaj validado manualmente",
    ("tjms", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGEsaj validado manualmente",
    ("tjsp", "cjsg"): "eSAJ parser extrai labels HTML — OutputCJSGTJSP validado manualmente",
    # TJDFT: parser passthrough do JSON da API.
    ("tjdft", "cjsg"): "TJDFT parser e passthrough do JSON — shape delegado ao backend",
    # TJSP cpopg/cposg retornam 4 DataFrames; Output e pivot.
    ("tjsp", "cpopg"): "TJSP cpopg retorna 4 DataFrames — Output cobre apenas o pivot",
    ("tjsp", "cposg"): "TJSP cposg retorna 4 DataFrames — Output cobre apenas o pivot",
    # Agregadores com backend rico — Output e pivot + extra=allow.
    ("datajud", "listar_processos"): "DataJud passthrough ES _source — extra=allow e o contrato",
    ("jusbr", "cpopg"): "JusBR passthrough PDPJ-CNJ — extra=allow e o contrato",
    ("jusbr", "download_documents"): (
        "JusBR download_documents passthrough — extra=allow e o contrato"
    ),
    ("comunica_cnj", "listar_comunicacoes"): (
        "ComunicaCNJ passthrough JSON da API — extra=allow e o contrato"
    ),
}


def _parser_sources(tribunal: str, endpoint: str) -> str:
    """Concatena source de todos os modulos de parser relevantes para ``tribunal``.

    Tenta varias convencoes:
    - ``juscraper.courts.<trib>.parse`` (convencao #84)
    - ``juscraper.courts.<trib>.<endpoint>_parse`` (TJSP tem cjsg_parse, cjpg_parse)
    - ``juscraper.aggregators.<name>.parse``
    - ``juscraper.courts.<trib>.client`` (fallback, caso cjsg_parse seja metodo)
    """
    sources: list[str] = []
    candidates = [
        f"juscraper.courts.{tribunal}.parse",
        f"juscraper.courts.{tribunal}.{endpoint}_parse",
        f"juscraper.aggregators.{tribunal}.parse",
        f"juscraper.courts.{tribunal}.client",
    ]
    for module_path in candidates:
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            continue
        try:
            sources.append(inspect.getsource(mod))
        except (OSError, TypeError):
            continue
    return "\n".join(sources)


def _own_fields(output_cls: type[BaseModel]) -> Iterable[str]:
    """Campos do Output que nao sao herdados de bases contratuais.

    Considera herdados os campos de :class:`OutputCJSGBase` e
    :class:`OutputCnjConsultaBase` — ja sao contrato universal e nao
    precisam aparecer no parser concreto (a garantia e estrutural).
    Tambem considera herdados os mixins de :mod:`juscraper.schemas.mixins`,
    que foram promovidos por evidencia (>=10 e >=9 parsers).
    """
    fields = set(output_cls.model_fields.keys())
    # Remove campos das bases.
    fields -= BASE_FIELDS_CJSG | BASE_FIELDS_CONSULTA
    # Remove campos dos mixins de Output (relator, orgao_julgador,
    # data_publicacao) — o teste os cobre indiretamente: se o tribunal
    # herda o mixin, significa que o parser entrega. Os mixins ja foram
    # auditados caso a caso na subida.
    fields -= {"relator", "orgao_julgador", "data_publicacao"}
    return fields


def _resolve_output(module_path: str, class_name: str) -> type[BaseModel]:
    mod = importlib.import_module(module_path)
    output_cls: type[BaseModel] = getattr(mod, class_name)
    return output_cls


COURT_NAMES = {name for name, _cls in _iter_court_scrapers()}
AGG_NAMES = {name for name, _cls in _iter_aggregator_scrapers()}

COURT_CASES = [
    pytest.param(name, endpoint, module_path, class_name, id=f"{name}.{endpoint}")
    for (name, endpoint), (module_path, class_name) in EXPECTED_COURT_OUTPUT_SCHEMAS.items()
    if name in COURT_NAMES
]

AGG_CASES = [
    pytest.param(name, endpoint, module_path, class_name, id=f"{name}.{endpoint}")
    for (name, endpoint), (module_path, class_name) in EXPECTED_AGGREGATOR_OUTPUT_SCHEMAS.items()
    if name in AGG_NAMES
]


@pytest.mark.parametrize(
    "name,endpoint,module_path,class_name", COURT_CASES + AGG_CASES
)
def test_output_fields_appear_in_parser_source(
    name, endpoint, module_path, class_name
):
    """Cada campo nao-herdado do Output aparece como string literal no source do parser."""
    reason = SKIP_REASONS.get((name, endpoint))
    if reason:
        pytest.skip(reason)

    output_cls = _resolve_output(module_path, class_name)
    source = _parser_sources(name, endpoint)
    if not source:
        pytest.skip(f"nenhum modulo de parser encontrado para {name}")

    missing = [
        field for field in _own_fields(output_cls)
        if f'"{field}"' not in source and f"'{field}'" not in source
    ]

    assert not missing, (
        f"{class_name} declara campos que nao aparecem em nenhum parser de {name}: "
        f"{sorted(missing)}. Possivel drift: Output foi inchado alem do que o "
        "parser entrega, ou o parser foi alterado e o Output nao acompanhou."
    )


def test_output_coverage_mapping_matches_input_mapping():
    """EXPECTED_COURT_OUTPUT_SCHEMAS nao tem entradas orfas nem faltando."""
    from tests.schemas.test_schema_coverage import EXPECTED_COURT_SCHEMAS

    input_keys = {
        k for k in EXPECTED_COURT_SCHEMAS
        # cjsg_ementa nao tem Output separado (retorna string, nao DataFrame)
        if k[1] != "cjsg_ementa"
    }
    output_keys = set(EXPECTED_COURT_OUTPUT_SCHEMAS)
    missing_output = input_keys - output_keys
    extra_output = output_keys - input_keys
    assert not missing_output, (
        f"Sem Output mapeado para: {sorted(missing_output)}"
    )
    assert not extra_output, (
        f"Output mapeado para endpoint inexistente: {sorted(extra_output)}"
    )
