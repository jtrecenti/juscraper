import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.juscraper.tjsp_scraper import TJSP_Scraper

def test_search_jurisprudencia_basic():
    scraper = TJSP_Scraper()
    resultados = scraper.cjsg("direito civil")
    assert isinstance(resultados, list)
    assert len(resultados) > 0
    for item in resultados:
        assert "ementa" in item
        assert item["ementa"]

def test_search_jurisprudencia_parametros():
    scraper = TJSP_Scraper()
    resultados = scraper.cjsg("família", classe=None, assunto=None)
    assert isinstance(resultados, list)
    assert len(resultados) > 0
    for item in resultados:
        assert "ementa" in item
        assert item["ementa"]

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
