"""Testes ao vivo do ``cpopg`` do TRF1 (API JSON da consulta pública).

Marcados ``integration``; rodam com ``pytest -m integration tests/trf1``. Em
16/11/2026 a API respondeu sem bloqueio a requisições de IP de datacenter; o
marker ``anti_bot`` continua para que um bloqueio futuro vire xfail, e não
falha de regressão.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import juscraper as jus

pytestmark = pytest.mark.anti_bot

# ``_PAGINADO`` tem 55 movimentações (4 páginas de 15); ``_NORMAL``, 106.
_PAGINADO_CNJ = "10030632720234013304"
_NORMAL_CNJ = "10088283520214013502"


@pytest.mark.integration
def test_cpopg_traz_processo_com_todas_as_movimentacoes() -> None:
    """Consulta real: colunas preenchidas e movimentações de todas as páginas."""
    df = jus.scraper("trf1", sleep_time=0.5).cpopg([_NORMAL_CNJ, _PAGINADO_CNJ])
    assert list(df["id_cnj"]) == [_NORMAL_CNJ, _PAGINADO_CNJ]
    assert list(df["motivo_falha"]) == [None, None]
    normal, paginado = df.iloc[0], df.iloc[1]
    assert normal["processo"] == "1008828-35.2021.4.01.3502"
    assert paginado["processo"] == "1003063-27.2023.4.01.3304"
    assert normal["classe"]
    assert normal["orgao_julgador"]
    assert len(paginado["movimentacoes"]) > 15
    assert len({(m["data"], m["descricao"]) for m in paginado["movimentacoes"]}) > 15
    assert paginado["polo_ativo"]
    assert paginado["documentos"]


@pytest.mark.integration
def test_cpopg_processo_ausente_vira_linha_so_com_id_cnj() -> None:
    """CNJ que a consulta pública não acha sai com ``id_cnj`` e ``motivo_falha`` ``None``."""
    missing_cnj = "00000000019994010000"
    df = jus.scraper("trf1", sleep_time=0.5).cpopg(missing_cnj)
    row = df.iloc[0]
    assert row["id_cnj"] == missing_cnj
    assert pd.isna(row["processo"])
    assert row["motivo_falha"] is None


@pytest.mark.integration
def test_cpopg_download_pecas_grava_pdfs(tmp_path) -> None:
    """``download_pecas=True`` grava o PDF de cada documento listado."""
    df = jus.scraper("trf1", sleep_time=0.5).cpopg(_PAGINADO_CNJ, download_pecas=True, diretorio=str(tmp_path))
    row = df.iloc[0]
    assert row["pecas_falhas"] == []
    assert len(row["pecas"]) == len(row["documentos"]) > 0
    for caminho in row["pecas"]:
        assert Path(caminho).read_bytes().startswith(b"%PDF")
