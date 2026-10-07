"""Integração do ``cpopg`` e do ``cposg`` do TRF3 contra a API real.

Marcados ``integration``; o ``pytest`` padrão os exclui. Exercitam o mesmo
caminho que os contratos simulam.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import juscraper as jus
from tests._helpers import assert_no_mojibake

# A consulta pública do TRF3 fica atrás do Akamai: de IPs de datacenter/CI o
# portal devolve 403 ``Access Denied`` e o scraper levanta
# ``BotChallengeBlockedError``. O marker ``anti_bot`` faz o conftest converter
# esse bloqueio em xfail (falha ambiental, não regressão). Ver issue #292.
pytestmark = [pytest.mark.anti_bot, pytest.mark.integration]

# JEF de Barueri com mais de 15 movimentações, que exercita a paginação.
_CNJ_1G = "50035362120254036342"
# Cumprimento de sentença no 1º grau e apelação cível no 2º grau.
_CNJ_2G = "50211226520184036100"


def test_cpopg_traz_todas_as_movimentacoes() -> None:
    """Processo real com mais de 15 movimentações devolve todas, sem repetir página."""
    df = jus.scraper("trf3", sleep_time=0.5).cpopg(_CNJ_1G)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["processo"] == "5003536-21.2025.4.03.6342"
    assert row["classe"]
    assert row["polo_ativo"] and row["polo_passivo"]
    movs = row["movimentacoes"]
    assert len(movs) > 15, f"esperava mais de 15 movimentações, veio {len(movs)}"
    pares = [(m["data"], m["descricao"]) for m in movs]
    assert len(pares) == len(set(pares)), "movimentações repetidas: página pedida duas vezes"
    assert_no_mojibake(" ".join(m["descricao"] for m in movs), contexto="movimentações (integração)")


def test_cposg_traz_recurso_de_2o_grau() -> None:
    """O mesmo CNJ no 2º grau devolve a apelação, com a turma."""
    df = jus.scraper("trf3", sleep_time=0.5).cposg(_CNJ_2G)
    row = df.iloc[0]
    assert row["processo"] == "5021122-65.2018.4.03.6100"
    assert row["classe"].startswith("APELAÇÃO")
    assert row["orgao_julgador_colegiado"]
    assert row["movimentacoes"]


def test_cpopg_download_pecas_grava_pdfs(tmp_path) -> None:
    """``download_pecas=True`` grava um PDF por documento e preenche ``pecas``."""
    df = jus.scraper("trf3", sleep_time=0.5).cpopg(_CNJ_1G, download_pecas=True, diretorio=str(tmp_path))
    salvos = df.iloc[0]["pecas"]
    assert len(salvos) == len(df.iloc[0]["documentos"]) > 0
    for caminho in salvos:
        assert caminho.endswith(".pdf")
        assert Path(caminho).read_bytes().startswith(b"%PDF")
