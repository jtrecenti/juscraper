"""Contrato generico exercitando cada schema pydantic mapeado.

Complementa os testes pontuais (:mod:`tests.schemas.test_cjsg_schemas`) com
afirmacoes que valem para **todo** schema Input/Output mapeado em
:mod:`tests.schemas.test_schema_coverage`. Especificamente:

- todo ``Input*`` rejeita ``extra_forbidden`` com um kwarg obviamente invalido;
- todo ``Input*`` de endpoint de busca aceita ``pesquisa="x"`` (quando o
  campo existe e nao e sobrescrito com default ``""``);
- todo ``Input*`` de consulta aceita ``id_cnj="x"`` (quando o campo existe);
- todo ``Output*`` correspondente tolera colunas extras (``extra="allow"``).

Os testes individuais mais detalhados (defaults, Literals, campos rejeitados
por tribunal especifico) continuam em :mod:`tests.schemas.test_cjsg_schemas`
para o conjunto wired.
"""
from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError

from tests.schemas.test_schema_coverage import EXPECTED_AGGREGATOR_SCHEMAS, EXPECTED_COURT_SCHEMAS


def _resolve(module_path: str, class_name: str):
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def _smart_payload(schema_cls) -> dict:
    """Minimum kwargs to instantiate the schema without missing-field errors."""
    payload: dict = {}
    fields = schema_cls.model_fields
    for name, info in fields.items():
        if info.is_required():
            if name == "pesquisa":
                payload[name] = "termo"
            elif name == "id_cnj":
                payload[name] = "1000000-00.2024.8.26.0100"
            elif name == "token":
                payload[name] = "tok"
            elif name == "uuid":
                payload[name] = "abc-123"
            elif name == "base_df":
                import pandas as pd

                payload[name] = pd.DataFrame()
            else:
                payload[name] = "x"
    return payload


ALL_INPUTS = [
    (k, module_path, class_name)
    for k, (module_path, class_name) in {
        **EXPECTED_COURT_SCHEMAS,
        **EXPECTED_AGGREGATOR_SCHEMAS,
    }.items()
]


@pytest.mark.parametrize(
    "key,module_path,class_name",
    ALL_INPUTS,
    ids=[f"{k[0]}.{k[1]}" for k, _, _ in ALL_INPUTS],
)
def test_input_rejects_unknown_kwarg(key, module_path, class_name):
    """Todo Input mapeado rejeita um kwarg desconhecido com ``extra_forbidden``."""
    schema_cls = _resolve(module_path, class_name)
    payload = _smart_payload(schema_cls)
    payload["_parametro_que_nao_existe_"] = "x"
    with pytest.raises(ValidationError) as exc_info:
        schema_cls(**payload)
    assert any(
        err["type"] == "extra_forbidden" for err in exc_info.value.errors()
    ), f"{class_name} aceitou _parametro_que_nao_existe_ (extra_forbidden esperado)"


@pytest.mark.parametrize(
    "key,module_path,class_name",
    ALL_INPUTS,
    ids=[f"{k[0]}.{k[1]}" for k, _, _ in ALL_INPUTS],
)
def test_input_minimum_payload_instantiable(key, module_path, class_name):
    """Todo Input mapeado e instanciavel com o minimo de campos requeridos."""
    schema_cls = _resolve(module_path, class_name)
    payload = _smart_payload(schema_cls)
    try:
        model = schema_cls(**payload)
    except ValidationError as exc:
        pytest.fail(
            f"{class_name} nao instancia com payload minimo {payload}:\n{exc}"
        )
    assert model is not None


# Outputs: garante que ``extra="allow"`` esta vigente e classe instanciavel.
OUTPUT_MODULES = {
    # (tribunal_code, endpoint) -> (module_path, output_class_name) — mesma
    # granularidade dos Inputs, so que Output.
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
    ("datajud", "listar_processos"): (
        "juscraper.aggregators.datajud.schemas",
        "OutputListarProcessosDataJud",
    ),
    ("jusbr", "cpopg"): (
        "juscraper.aggregators.jusbr.schemas",
        "OutputCPOPGJusBR",
    ),
    ("jusbr", "download_documents"): (
        "juscraper.aggregators.jusbr.schemas",
        "OutputDownloadDocumentsJusBR",
    ),
}


def _output_payload(schema_cls) -> dict:
    out: dict = {}
    for name, info in schema_cls.model_fields.items():
        if info.is_required():
            if name in ("processo", "id_cnj"):
                out[name] = "1000000-00.2024.8.26.0100"
            elif name == "ementa":
                out[name] = "Texto da ementa."
            elif name == "id_processo":
                out[name] = "1000"
            elif name == "numeroProcesso":
                out[name] = "0000000-00.0000.0.00.0000"
            elif name == "processo_pesquisado":
                out[name] = "0000000-00.0000.0.00.0000"
            elif name == "numero_processo":
                out[name] = "0000000-00.0000.0.00.0000"
            else:
                out[name] = "x"
    return out


@pytest.mark.parametrize(
    "key,module_path,class_name",
    [(k, mp, cn) for k, (mp, cn) in OUTPUT_MODULES.items()],
    ids=[f"{k[0]}.{k[1]}" for k in OUTPUT_MODULES],
)
def test_output_allows_extras(key, module_path, class_name):
    """Todo Output mapeado tolera colunas nao listadas (``extra="allow"``)."""
    schema_cls = _resolve(module_path, class_name)
    payload = _output_payload(schema_cls)
    payload["coluna_especifica_do_tribunal_x"] = "foo"
    model = schema_cls(**payload)
    # extras ficam acessiveis via __pydantic_extra__
    assert hasattr(model, "coluna_especifica_do_tribunal_x") or (
        getattr(model, "model_extra", {}) or {}
    ).get("coluna_especifica_do_tribunal_x") == "foo"


def test_tjgo_output_accepts_parser_shape():
    """OutputCJSGTJGO aceita o shape real do parser (sem ``ementa``, com ``texto``).

    O parser do TJGO (``src/juscraper/courts/tjgo/parse.py``) entrega
    o conteudo do documento em ``texto`` e nao produz coluna ``ementa``,
    ao contrario dos demais cjsg. O schema tem que refletir isso em vez
    de herdar ``ementa: str`` required de :class:`OutputCJSGBase`.
    """
    from juscraper.courts.tjgo.schemas import OutputCJSGTJGO

    row = {
        "processo": "0000000-00.2024.8.09.0001",
        "id_arquivo": "abc",
        "serventia": "1a Vara",
        "relator": "Fulano",
        "tipo_ato": "Decisao",
        "data_publicacao": "2024-01-15",
        "texto": "Conteudo do documento ...",
    }
    model = OutputCJSGTJGO(**row)
    assert model.processo == row["processo"]
    assert model.ementa is None
