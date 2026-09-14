"""Live integration tests for STF (need network and the ``stf`` extra)."""
import pytest

import juscraper as jus

pytestmark = pytest.mark.integration
pytest.importorskip("playwright")


@pytest.fixture(scope="module")
def stf():
    return jus.scraper("stf")


def test_contar_decisoes_ao_vivo(stf):
    df = stf.contar_decisoes("pejotização", classe="Rcl")
    assert df.iloc[0]["faceta"] == "total"
    assert df.iloc[0]["n"] > 0


def test_listar_decisoes_ao_vivo(stf):
    df = stf.listar_decisoes("pejotização", classe="Rcl", paginas=1, tamanho_pagina=5)
    assert len(df) == 5
    assert set(df["classe"]) == {"Rcl"}
    assert df["decisao_texto"].notna().all()
