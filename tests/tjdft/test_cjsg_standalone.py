# Arquivo migrado e padronizado conforme outros tribunais
# Conteúdo transferido de test_tjdft_cjsg_standalone.py

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
from juscraper.tjdft_scraper import TJDFT_Scraper

# Teste standalone padronizado para cjsg do TJDFT

def test_cjsg_standalone():
    scraper = TJDFT_Scraper()
    df = scraper.cjsg('direito penal', paginas=1)
    print(df.head())
    assert not df.empty
    assert "ementa" in df.columns
    assert "processo" in df.columns

if __name__ == "__main__":
    test_cjsg_standalone()
