# Arquivo migrado e padronizado conforme outros tribunais
# Conteúdo transferido de test_tjdft_cjsg_draft.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
import pytest
from juscraper.tjdft_scraper import TJDFT_Scraper

# Teste padronizado para cjsg do TJDFT

def test_cjsg_basico():
    scraper = TJDFT_Scraper()
    df = scraper.cjsg(
        termo="direito penal",
        paginas=1,
        sinonimos=True,
        espelho=True,
        inteiro_teor=False
    )
    print(df.head())
    assert not df.empty
    assert "ementa" in df.columns
    assert "processo" in df.columns
