r"""Texto corrido sai dos parsers sem ``\r``, ``\xa0`` e caracteres invisíveis.

Cada caso roda o parser sobre um sample real duas vezes: com
``normalizar_texto`` (ou ``normalizar_colunas_texto``) trocada pela identidade,
para provar que a coluna trazia o problema, e do jeito normal. A saída normal
tem de ser exatamente a bruta passada por ``normalizar_texto``: nada além
desses caracteres muda, e as quebras de linha ficam.

O cjsg do eSAJ tem os testes em ``tests/_esaj/test_parse_granular.py``.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, cast
from unittest import mock

import pandas as pd
import pytest
import requests

from juscraper.aggregators.comunica_cnj import parse as comunica_parse
from juscraper.aggregators.falcao import parse as falcao_parse
from juscraper.core.parse_utils import normalizar_texto
from juscraper.courts._esaj import cjpg_parse as esaj_cjpg_parse
from juscraper.courts.stf import parse as stf_parse
from juscraper.courts.tjba import parse as tjba_parse
from juscraper.courts.tjdft import parse as tjdft_parse
from juscraper.courts.tjes import parse as tjes_parse
from juscraper.courts.tjpb import parse as tjpb_parse
from juscraper.courts.tjpi import parse as tjpi_parse
from juscraper.courts.tjrj import parse as tjrj_parse
from juscraper.courts.tjrr import parse as tjrr_parse
from juscraper.courts.tjrr.download import _extract_cdata
from juscraper.courts.tjrs import parse as tjrs_parse

_RAIZ = Path(__file__).parent
_PROIBIDOS = re.compile("[\r\xa0\xad\u200b‌‍]")


def _caminho(tribunal: str, arquivo: str) -> Path:
    return _RAIZ / tribunal / "samples" / arquivo


def _json(tribunal: str, arquivo: str) -> Any:
    # Em bytes: ``read_text`` trocaria o ``\r\n`` literal de um sample.
    return json.loads(_caminho(tribunal, arquivo).read_bytes().decode("utf-8"))


def _resposta(tribunal: str, arquivo: str) -> requests.Response:
    resposta = mock.Mock(spec=requests.Response)
    resposta.json.return_value = _json(tribunal, arquivo)
    return cast(requests.Response, resposta)


@dataclass(frozen=True)
class Caso:
    modulo: ModuleType
    parsear: Callable[[], pd.DataFrame]
    colunas: tuple[str, ...]
    quebra_de_linha: bool = True
    intactas: tuple[str, ...] = field(default=())
    """Colunas de HTML que ficam como vieram, com ``\\r``."""


CASOS = {
    "tjsp-cjpg": Caso(
        esaj_cjpg_parse,
        lambda: esaj_cjpg_parse.cjpg_parse_single(_caminho("tjsp", "cjpg/results_normal_page_01.html")),
        ("decisao",),
    ),
    "tjms-cjpg": Caso(
        esaj_cjpg_parse,
        lambda: esaj_cjpg_parse.cjpg_parse_single(_caminho("tjms", "cjpg/results_normal_page_01.html")),
        ("decisao",),
    ),
    "tjba-cjsg": Caso(
        tjba_parse,
        lambda: tjba_parse.cjsg_parse([_json("tjba", "cjsg/results_normal_page_01.json")]),
        ("ementa",),
        quebra_de_linha=False,
    ),
    "tjdft-cjsg": Caso(
        tjdft_parse,
        lambda: pd.DataFrame(tjdft_parse.cjsg_parse(_json("tjdft", "cjsg/results_normal_page_01.json")["registros"])),
        ("ementa",),
    ),
    "tjes-cjsg": Caso(
        tjes_parse,
        lambda: tjes_parse.cjsg_parse([_json("tjes", "cjsg/results_legado_page_01.json")]),
        ("ementa", "acordao"),
    ),
    "tjpb-cjsg": Caso(
        tjpb_parse,
        lambda: tjpb_parse.cjsg_parse_manager([_json("tjpb", "cjsg/results_normal_page_01.json")]),
        ("ementa",),
        quebra_de_linha=False,
    ),
    "tjpi-cjsg": Caso(
        tjpi_parse,
        lambda: tjpi_parse.cjsg_parse_manager([_caminho("tjpi", "cjsg/results_normal_page_01.html").read_text()]),
        ("inteiro_teor", "ementa"),
    ),
    "tjrj-cjsg": Caso(
        tjrj_parse,
        lambda: tjrj_parse.cjsg_parse([_json("tjrj", "cjsg/xhr_page_01.json")["d"]]),
        ("ementa",),
    ),
    "tjrr-cjsg": Caso(
        tjrr_parse,
        lambda: tjrr_parse.cjsg_parse_manager(
            [_extract_cdata(_caminho("tjrr", "cjsg/step_02_search.html").read_text())]
        ),
        ("ementa",),
        quebra_de_linha=False,
    ),
    "tjrs-cjsg": Caso(
        tjrs_parse,
        lambda: tjrs_parse.cjsg_parse_manager([_json("tjrs", "cjsg/single_page.json")]),
        ("ementa", "ementa_text", "ementa_referencia"),
    ),
    "stf-listar_decisoes": Caso(
        stf_parse,
        lambda: pd.DataFrame(stf_parse.parse_decisoes([
            _json("stf", "listar_decisoes/single_page.json"),
            _json("stf", "listar_decisoes/acordaos.json"),
        ])),
        (
            "decisao_texto",
            "partes_lista_texto",
            "documental_publicacao_lista_texto",
            "documental_observacao_texto",
            "acordao_ata",
        ),
        intactas=("documental_observacao_html",),
    ),
    "comunica_cnj-listar_comunicacoes": Caso(
        comunica_parse,
        lambda: pd.DataFrame(comunica_parse.parse_items(
            _resposta("comunica_cnj", "listar_comunicacoes/results_normal_page_01.json")
        )),
        ("texto",),
    ),
    "falcao-listar_decisoes": Caso(
        falcao_parse,
        lambda: pd.DataFrame(falcao_parse.parse_documentos(
            _json("falcao", "pesquisa/precedentes_normal.json"), "precedentes"
        )),
        ("textoDecisaoAdmissao", "textoEmentaAdmissao", "textoEmentaMerito"),
        intactas=("conteudoDecisao",),
    ),
}


def _sem_normalizar(monkeypatch: pytest.MonkeyPatch, modulo: ModuleType) -> None:
    if hasattr(modulo, "normalizar_colunas_texto"):
        monkeypatch.setattr(modulo, "normalizar_colunas_texto", lambda df, _colunas: df)
    else:
        monkeypatch.setattr(modulo, "normalizar_texto", lambda texto: texto)


def _com_problema(serie: pd.Series) -> bool:
    return any(isinstance(valor, str) and _PROIBIDOS.search(valor) for valor in serie)


@pytest.mark.parametrize("caso", CASOS.values(), ids=CASOS.keys())
def test_texto_corrido_normalizado(monkeypatch, caso):
    with monkeypatch.context() as contexto:
        _sem_normalizar(contexto, caso.modulo)
        bruto = caso.parsear()
    resultado = caso.parsear()

    assert any(_com_problema(bruto[coluna]) for coluna in caso.colunas)
    for coluna in caso.colunas:
        assert not _com_problema(resultado[coluna]), coluna
        esperado = bruto[coluna].map(normalizar_texto)
        pd.testing.assert_series_equal(resultado[coluna], esperado, check_dtype=False)
    if caso.quebra_de_linha:
        assert any(resultado[coluna].str.contains("\n").any() for coluna in caso.colunas)
    for coluna in caso.intactas:
        assert resultado[coluna].str.contains("\r").any(), coluna
