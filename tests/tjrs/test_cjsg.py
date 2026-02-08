import pytest
import pandas as pd
from juscraper.courts.tjrs.client import TJRSScraper


@pytest.mark.integration
def test_cjsg_basic_dataframe():
    scraper = TJRSScraper()
    df = scraper.cjsg("direito civil")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_parametros_secao():
    scraper = TJRSScraper()
    df_civel = scraper.cjsg("família", secao="civel")
    df_crime = scraper.cjsg("homicídio", secao="crime")
    assert isinstance(df_civel, pd.DataFrame)
    assert not df_civel.empty
    assert "ementa" in df_civel.columns
    assert df_civel["ementa"].notnull().all()
    assert isinstance(df_crime, pd.DataFrame)
    assert not df_crime.empty
    assert "ementa" in df_crime.columns
    assert df_crime["ementa"].notnull().all()


@pytest.mark.integration
def test_cjsg_dataframe():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão")
    print("DataFrame columns:", df.columns)
    print("First rows:\n", df.head())
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_paginas_range():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão", paginas=range(0, 3))
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) > 10
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_paginas_int():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão", paginas=2)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert len(df) > 10
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


@pytest.mark.integration
def test_cjsg_paginas_range_exact_count():
    scraper = TJRSScraper()
    df = scraper.cjsg("acórdão", paginas=range(0, 3))
    print(f"Número de linhas retornadas: {len(df)}")
    duplicados = df.duplicated().sum()
    print(f"Duplicatas: {duplicados}")
    assert len(df) == 30, f"Esperado 30 linhas (3 páginas), mas retornou {len(df)}"
    assert duplicados == 0, f"Há duplicatas nos resultados: {duplicados}"


if __name__ == "__main__":
    pytest.main([__file__])
