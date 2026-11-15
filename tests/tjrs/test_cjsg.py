import pandas as pd
import pytest

from juscraper.courts.tjrs.client import TJRSScraper


@pytest.mark.integration
def test_cjsg_basic_dataframe():
    scraper = TJRSScraper()
    df = scraper.cjsg("direito civil", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_parametros_secao():
    scraper = TJRSScraper()
    df_civel = scraper.cjsg("família", paginas=1, secao="civel")
    df_crime = scraper.cjsg("homicídio", paginas=1, secao="crime")
    assert isinstance(df_civel, pd.DataFrame)
    assert not df_civel.empty
    assert "ementa" in df_civel.columns
    assert df_civel["ementa"].notnull().all()
    assert isinstance(df_crime, pd.DataFrame)
    assert not df_crime.empty
    assert "ementa" in df_crime.columns
    assert df_crime["ementa"].notnull().all()
    # O filtro precisa restringir de fato a seção, não só devolver linhas.
    assert (df_civel["secao"] == "CIVEL").all()
    assert (df_crime["secao"] == "CRIME").all()


@pytest.mark.integration
def test_cjsg_paginas_range():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão", paginas=range(1, 4))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 30, f"Esperado 30 linhas (3 páginas), mas retornou {len(df)}"
    assert df.duplicated().sum() == 0
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_paginas_int():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão", paginas=2)
    assert len(df) == 20, f"Esperado 20 linhas (2 páginas), mas retornou {len(df)}"


if __name__ == "__main__":
    pytest.main([__file__])
