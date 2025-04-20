import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.juscraper.tjrs_scraper import TJRS_Scraper

def test_cjsg_basic_dataframe():
    scraper = TJRS_Scraper()
    df = scraper.cjsg("direito civil")
    import pandas as pd
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0

def test_cjsg_parametros_secao():
    scraper = TJRS_Scraper()
    df_civel = scraper.cjsg("família", secao="civel")
    df_crime = scraper.cjsg("homicídio", secao="crime")
    import pandas as pd
    assert isinstance(df_civel, pd.DataFrame)
    assert not df_civel.empty
    assert "ementa" in df_civel.columns
    assert df_civel["ementa"].notnull().all()
    assert isinstance(df_crime, pd.DataFrame)
    assert not df_crime.empty
    assert "ementa" in df_crime.columns
    assert df_crime["ementa"].notnull().all()

def test_cjsg_dataframe():
    scraper = TJRS_Scraper()
    df = scraper.cjsg("acórdão")
    import pandas as pd
    print("DataFrame columns:", df.columns)
    print("First rows:\n", df.head())
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    # Permite que algumas urls estejam ausentes, mas pelo menos uma deve existir
    assert df["url"].notnull().sum() > 0

def test_cjsg_paginas_range():
    scraper = TJRS_Scraper()
    df = scraper.cjsg("acórdão", paginas=range(0, 3))
    import pandas as pd
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Agora, para queries abrangentes, o resultado deve ser maior que 10 (esperado 20~30, se houver resultados suficientes)
    assert len(df) > 10
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0


def test_cjsg_paginas_int():
    scraper = TJRS_Scraper()
    df = scraper.cjsg("acórdão", paginas=2)
    import pandas as pd
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    # Agora, para queries abrangentes, o resultado deve ser maior que 10 (esperado 20, se houver resultados suficientes)
    assert len(df) > 10
    assert {"ementa", "url"}.issubset(set(df.columns))
    assert df["ementa"].notnull().all()
    assert df["url"].notnull().sum() > 0

def test_cjsg_paginas_range_exact_count():
    scraper = TJRS_Scraper()
    df = scraper.cjsg("acórdão", paginas=range(0, 3))
    print(f"Número de linhas retornadas: {len(df)}")
    duplicados = df.duplicated().sum()
    print(f"Duplicatas: {duplicados}")
    # O correto é exigir 30 linhas (se houver no banco). Se não houver, aceita menos, mas nunca 10 se há mais resultados disponíveis.
    assert len(df) == 30, f"Esperado 30 linhas (3 páginas), mas retornou {len(df)}"
    assert duplicados == 0, f"Há duplicatas nos resultados: {duplicados}"

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
