"""Integração do ``cjpg`` do TJTO: 2 POSTs (o limite do WAF está em ``test_cjsg.py``)."""
import pytest

from juscraper.courts.tjto.client import TJTOScraper


@pytest.mark.integration
def test_cjpg_duas_paginas():
    scraper = TJTOScraper()
    brutos = scraper.cjpg_download("dano moral", paginas=range(1, 3))
    df = scraper.cjpg_parse(brutos)
    assert len(brutos) == 2
    assert {"processo", "classe", "relator", "data_julgamento"}.issubset(df.columns)
    assert len(df) == 40
    assert df["uuid"].is_unique
