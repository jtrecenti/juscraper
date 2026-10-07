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
