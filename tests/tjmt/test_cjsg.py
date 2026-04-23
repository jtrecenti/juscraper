import pandas as pd
import pytest

from juscraper.courts.tjmt.client import TJMTScraper


@pytest.mark.integration
def test_cjsg_basic_dataframe():
    scraper = TJMTScraper()
    df = scraper.cjsg("direito", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "processo", "relator"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()


@pytest.mark.integration
def test_cjsg_colunas_esperadas():
    scraper = TJMTScraper()
    df = scraper.cjsg("direito", paginas=1)
    colunas_minimas = {
        "id", "tipo", "ementa", "processo", "classe",
        "assunto", "relator", "orgao_julgador",
        "data_julgamento", "data_publicacao",
    }
    assert colunas_minimas.issubset(set(df.columns))


@pytest.mark.integration
def test_cjsg_paginacao():
    scraper = TJMTScraper()
    df_1 = scraper.cjsg("dano moral", paginas=1)
    df_2 = scraper.cjsg("dano moral", paginas=range(1, 3))
    assert len(df_2) > len(df_1)


@pytest.mark.integration
def test_cjsg_paginas_int():
    scraper = TJMTScraper()
    df_int = scraper.cjsg("direito", paginas=2)
    df_range = scraper.cjsg("direito", paginas=range(1, 3))
    assert len(df_int) == len(df_range)


@pytest.mark.integration
def test_cjsg_download_e_parse():
    scraper = TJMTScraper()
    brutos = scraper.cjsg_download("direito", paginas=1)
    assert isinstance(brutos, list)
    assert len(brutos) > 0
    dados = scraper.cjsg_parse(brutos)
    assert isinstance(dados, list)
    assert len(dados) > 0
    df = pd.DataFrame(dados)
    assert "ementa" in df.columns


if __name__ == "__main__":
    pytest.main([__file__])
