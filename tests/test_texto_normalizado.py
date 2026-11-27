r"""Texto corrido sai dos parsers sem ``\r``, ``\xa0`` e caracteres invisíveis.

Cada caso roda o parser sobre um sample real, lido como em
``tests/schemas/test_output_columns.py::LEITURAS``, duas vezes: com
``normalizar_texto`` (ou ``normalizar_colunas_texto``) trocada pela identidade,
para provar que a coluna trazia o problema, e do jeito normal. A saída normal
tem de ser exatamente a bruta passada por ``normalizar_texto``: nada além
desses caracteres muda, e as quebras de linha ficam.

O cjsg do eSAJ tem os testes em ``tests/_esaj/test_parse_granular.py``. A
ementa que passa por :func:`~juscraper.core.parse_utils.html_para_texto`
(TJRJ e os demais de ``tests/test_ementa_paragrafos.py``) é conferida lá, sem
``\r`` e ``\xa0``.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from types import ModuleType
from typing import Any

import pandas as pd
import pytest

import juscraper as jus
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
from juscraper.courts.tjrr import parse as tjrr_parse
from juscraper.courts.tjrs import parse as tjrs_parse
from tests.schemas.test_output_columns import LEITURAS, TESTS


@dataclass(frozen=True)
class Caso:
    tribunal: str
    endpoint: str
    arquivo: str
    modulo: ModuleType
    colunas: tuple[str, ...]
    quebra_de_linha: bool = True
    intactas: tuple[str, ...] = ()
    r"""Colunas de HTML que ficam como vieram, com ``\r``."""

    def parsear(self) -> pd.DataFrame:
        leitura = LEITURAS[(self.tribunal, self.endpoint)]
        parser = leitura.parser or getattr(jus.scraper(self.tribunal), f"{self.endpoint}_parse")
        caminho = TESTS / self.tribunal / "samples" / (leitura.pasta or self.endpoint) / self.arquivo
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            resultado = parser(*leitura.entrada(caminho))
        return resultado if isinstance(resultado, pd.DataFrame) else pd.DataFrame(resultado)


CASOS = [
    Caso("tjsp", "cjpg", "results_normal_page_01.html", esaj_cjpg_parse, ("decisao",)),
    Caso("tjms", "cjpg", "results_normal_page_01.html", esaj_cjpg_parse, ("decisao",)),
    Caso("tjba", "cjsg", "results_normal_page_01.json", tjba_parse, ("ementa",), quebra_de_linha=False),
    Caso("tjdft", "cjsg", "results_normal_page_01.json", tjdft_parse, ("ementa",)),
    Caso("tjes", "cjsg", "results_legado_page_01.json", tjes_parse, ("ementa", "acordao")),
    Caso("tjpb", "cjsg", "results_normal_page_01.json", tjpb_parse, ("ementa",), quebra_de_linha=False),
    Caso("tjpi", "cjsg", "results_normal_page_01.html", tjpi_parse, ("inteiro_teor", "resumo", "ementa")),
    Caso("tjrr", "cjsg", "step_02_search.html", tjrr_parse, ("ementa",), quebra_de_linha=False),
    Caso("tjrs", "cjsg", "single_page.json", tjrs_parse, ("ementa", "ementa_text", "ementa_referencia")),
    Caso(
        "stf",
        "listar_decisoes",
        "single_page.json",
        stf_parse,
        ("decisao_texto", "partes_lista_texto", "documental_publicacao_lista_texto", "documental_observacao_texto"),
        intactas=("documental_observacao_html",),
    ),
    Caso("stf", "listar_decisoes", "acordaos.json", stf_parse, ("acordao_ata",)),
    Caso("comunica_cnj", "listar_comunicacoes", "results_normal_page_01.json", comunica_parse, ("texto",)),
    Caso(
        "falcao",
        "listar_decisoes",
        "precedentes_normal.json",
        falcao_parse,
        ("textoDecisaoAdmissao", "textoEmentaAdmissao", "textoEmentaMerito"),
        intactas=("conteudoDecisao",),
    ),
]


def _sem_normalizar(monkeypatch: pytest.MonkeyPatch, modulo: ModuleType) -> None:
    if hasattr(modulo, "normalizar_colunas_texto"):
        monkeypatch.setattr(modulo, "normalizar_colunas_texto", lambda df, _colunas: df)
    else:
        monkeypatch.setattr(modulo, "normalizar_texto", lambda texto: texto)


def _textos(serie: pd.Series) -> list[str | None]:
    """Valores da coluna, com ``None`` no lugar de qualquer ausente (``None`` ou ``NaN``)."""
    return [valor if isinstance(valor, str) else None for valor in serie]


def _sujo(valor: Any) -> bool:
    if isinstance(valor, list):
        return any(_sujo(item) for item in valor)
    return isinstance(valor, str) and normalizar_texto(valor) != valor


@pytest.mark.parametrize("caso", CASOS, ids=[f"{c.tribunal}-{c.endpoint}-{c.arquivo}" for c in CASOS])
def test_texto_corrido_normalizado(monkeypatch, caso):
    with monkeypatch.context() as contexto:
        _sem_normalizar(contexto, caso.modulo)
        bruto = caso.parsear()
    resultado = caso.parsear()

    assert any(bruto[coluna].map(_sujo).any() for coluna in caso.colunas)
    for coluna in caso.colunas:
        assert _textos(resultado[coluna]) == [normalizar_texto(texto) for texto in _textos(bruto[coluna])], coluna
    if caso.quebra_de_linha:
        assert any(resultado[coluna].str.contains("\n").any() for coluna in caso.colunas)
    for coluna in caso.intactas:
        assert resultado[coluna].str.contains("\r").any(), coluna


def test_stf_normaliza_cada_item_dos_campos_texto_em_lista(monkeypatch):
    r"""``documental_legislacao_citada_texto`` vem como lista de textos com ``\r\n``."""
    caso = Caso("stf", "listar_decisoes", "single_page.json", stf_parse, ())
    coluna = "documental_legislacao_citada_texto"
    with monkeypatch.context() as contexto:
        _sem_normalizar(contexto, stf_parse)
        bruto = caso.parsear()[coluna].dropna()
    itens = [item for lista in caso.parsear()[coluna].dropna() for item in lista]

    assert bruto.map(_sujo).any()
    assert itens
    assert not any(_sujo(item) for item in itens)
    assert any("\n" in item for item in itens)
