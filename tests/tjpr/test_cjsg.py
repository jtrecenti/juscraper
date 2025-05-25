# Arquivo movido e padronizado conforme outros tribunais
# O conteúdo será transferido de test_tjpr_scraper.py e ajustado para o padrão cjsg

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))
import pytest
from juscraper.tjpr_scraper import TJPR_Scraper
import pandas as pd
from bs4 import BeautifulSoup

# Testes padronizados para o caso cjsg do TJPR

def test_cjsg_download_and_parse():
    scraper = TJPR_Scraper()
    # Baixa apenas uma página para teste rápido
    htmls = scraper.cjsg_download(termo="direito civil", paginas=1)
    assert isinstance(htmls, list)
    assert len(htmls) == 1
    html = htmls[0]
    assert "html" in html.lower() or "DOCTYPE" in html[:100]
    # Testa o parse do HTML
    df = scraper.cjsg_parse(htmls)
    if df.empty:
        print("\n==== HTML COMPLETO retornado para depuração ====")
        print(html[:10000])
        print("\n==== Fim do HTML ====")
        soup = BeautifulSoup(html, "html.parser")
        all_tables = soup.find_all("table")
        print(f"Tabelas encontradas: {len(all_tables)}")
        for idx, table in enumerate(all_tables):
            print(f"Tabela {idx}: {str(table)[:500]}")
            rows = table.find_all("tr")
            print(f"  Linhas na tabela: {len(rows)}")
    assert not df.empty, "DataFrame vazio! Veja o HTML acima para investigar."
    # Deve conter as colunas principais
    for col in ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]:
        assert col in df.columns
    # Deve haver ao menos um processo com ementa não vazia
    assert df["ementa"].str.len().max() > 0

def test_cjsg_interface():
    scraper = TJPR_Scraper()
    df = scraper.cjsg(termo="direito civil", paginas=1)
    if df.empty:
        print("\n==== DataFrame vazio na interface. ====")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "DataFrame vazio! Veja a saída do teste anterior."
    assert "ementa" in df.columns
    assert df["ementa"].str.len().max() > 0
