import pytest
import pandas as pd
from juscraper.courts.tjto.client import TJTOScraper


@pytest.mark.integration
def test_cjpg_basic_dataframe():
    scraper = TJTOScraper()
    df = scraper.cjpg("direito", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"processo", "classe", "relator", "data_julgamento"}.issubset(set(df.columns))


@pytest.mark.integration
def test_cjpg_paginacao():
    scraper = TJTOScraper()
    df_p1 = scraper.cjpg("dano moral", paginas=1)
    df_p2 = scraper.cjpg("dano moral", paginas=range(1, 3))
    assert len(df_p2) > len(df_p1)


@pytest.mark.integration
def test_cjpg_download_e_parse():
    scraper = TJTOScraper()
    brutos = scraper.cjpg_download("direito", paginas=1)
    assert isinstance(brutos, list)
    assert len(brutos) == 1
    df = scraper.cjpg_parse(brutos)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


@pytest.mark.integration
def test_cjpg_tipo_documento_sentencas():
    scraper = TJTOScraper()
    df = scraper.cjpg("direito", paginas=1, tipo_documento="sentencas")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


if __name__ == "__main__":
    pytest.main([__file__])
