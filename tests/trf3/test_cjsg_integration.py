"""Live integration tests for TRF3 ``cjsg`` (busca de jurisprudência).

Marked ``integration`` and skipped by default. The portal sits behind the
Akamai bot manager: from datacenter or CI IPs it answers 403 ``Access Denied``
and the scraper raises ``BotChallengeBlockedError``; the ``anti_bot`` marker
turns that block into xfail (environmental failure, not a regression).
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.trf3.cjsg_download import cjsg_n_results
from tests._helpers import assert_no_mojibake

pytestmark = [pytest.mark.integration, pytest.mark.anti_bot]

SEMESTRE = {"data_julgamento_inicio": "2026-01-01", "data_julgamento_fim": "2026-06-30"}


def test_cjsg_acordaos_duas_paginas() -> None:
    df = jus.scraper("trf3", sleep_time=1.0).cjsg("medicamento", paginas=range(1, 3), **SEMESTRE)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 20
    assert df["processo"].is_unique
    assert (df["base"] == "acordaos").all()
    assert df["ementa"].notna().all()
    assert df["data_julgamento"].between(pd.Timestamp("2026-01-01").date(), pd.Timestamp("2026-06-30").date()).all()
    assert_no_mojibake(" ".join(df["ementa"]), contexto="ementas TRF3 cjsg (integração)")


@pytest.mark.parametrize("base", ["turmas_recursais", "monocraticas", "monocraticas_turmas_recursais"])
def test_cjsg_outras_bases(base: str) -> None:
    df = jus.scraper("trf3", sleep_time=1.0).cjsg("medicamento", base=base, paginas=1, **SEMESTRE)
    assert len(df) == 10
    assert (df["base"] == base).all()
    assert df["ementa"].notna().all()
    assert df["relator"].notna().any()


def test_cjsg_filtro_relator_restringe() -> None:
    df = jus.scraper("trf3", sleep_time=1.0).cjsg("medicamento", relator="ANDRE NABARRETE", paginas=1, **SEMESTRE)
    assert len(df) > 0
    nomes = df["relator"].fillna("") + " " + df["relator_acordao"].fillna("")
    assert nomes.str.contains("NABARRETE").all()


def test_cjsg_filtro_orgao_primeira_secao() -> None:
    """The column value ``QUINTA TURMA - 1A. SEÇÃO`` selects the dropdown option.

    The search sends that option's pair, label ``5ª Turma`` and indexed name
    ``QUINTA TURMA - 1A``, so it also brings the recent documents labelled
    ``5ª Turma``, which the indexed name alone never finds.
    """
    df = jus.scraper("trf3", sleep_time=1.0).cjsg("medicamento", orgao_julgador="QUINTA TURMA - 1A. SEÇÃO", paginas=1)
    assert len(df) > 0
    assert df["orgao_julgador"].isin({"5ª Turma", "QUINTA TURMA - 1A. SEÇÃO"}).all()
    assert (df["orgao_julgador"] == "5ª Turma").any()


def test_cjsg_filtros_so_de_acordaos_restringem() -> None:
    """``numero_classe``, ``sistema_interamericano`` and ``legislacao`` reach the server.

    Measured on 2026-11-15: ``numclasse`` 1708075 finds ``Ap - APELAÇÃO CÍVEL
    - 1708075``; Corte IDH case 1 alone finds 7 documents (a search with no
    criterion is refused); the legislation panel's text for the Lei Pelé
    finds 4 documents.
    """
    trf3 = jus.scraper("trf3", sleep_time=1.0)

    df = trf3.cjsg(numero_classe="1708075", paginas=1)
    assert df["classe"].str.endswith(" - 1708075").any()

    # The case is the only criterion: had the server ignored it, the search would be refused.
    total = cjsg_n_results(trf3.cjsg_download(sistema_interamericano=1, paginas=1)[0])
    assert total is not None
    assert 0 < total < 1000

    df = trf3.cjsg(legislacao="LEI PELÉ FED LEI 9615 1998", paginas=1)
    assert len(df) > 0
    assert (df["ementa"].fillna("") + df["inteiro_teor"].fillna("")).str.contains("9615").any()
