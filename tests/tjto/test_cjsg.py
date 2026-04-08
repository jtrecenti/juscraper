import pytest
import pandas as pd
from juscraper.courts.tjto.client import TJTOScraper


@pytest.mark.integration
def test_cjsg_basic_dataframe():
    scraper = TJTOScraper()
    df = scraper.cjsg("direito", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert {"processo", "classe", "relator", "data_julgamento"}.issubset(set(df.columns))


@pytest.mark.integration
def test_cjsg_colunas_esperadas():
    scraper = TJTOScraper()
    df = scraper.cjsg("direito", paginas=1)
    colunas_esperadas = {
        "processo", "uuid", "classe", "tipo_julgamento", "assunto",
        "competencia", "relator", "data_autuacao", "data_julgamento",
        "processo_link",
    }
    assert colunas_esperadas.issubset(set(df.columns))


@pytest.mark.integration
def test_cjsg_paginacao():
    scraper = TJTOScraper()
    df_p1 = scraper.cjsg("dano moral", paginas=1)
    df_p2 = scraper.cjsg("dano moral", paginas=range(1, 3))
    assert len(df_p2) > len(df_p1)


@pytest.mark.integration
def test_cjsg_paginas_int():
    scraper = TJTOScraper()
    df_int = scraper.cjsg("direito", paginas=2)
    df_range = scraper.cjsg("direito", paginas=range(1, 3))
    assert len(df_int) == len(df_range)


@pytest.mark.integration
def test_cjsg_filtro_data():
    scraper = TJTOScraper()
    df = scraper.cjsg(
        "direito",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="30/06/2024",
        paginas=1,
    )
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


@pytest.mark.integration
def test_cjsg_download_e_parse():
    scraper = TJTOScraper()
    brutos = scraper.cjsg_download("direito", paginas=1)
    assert isinstance(brutos, list)
    assert len(brutos) == 1
    df = scraper.cjsg_parse(brutos)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


@pytest.mark.integration
def test_cjsg_tipo_documento_decisoes():
    scraper = TJTOScraper()
    df = scraper.cjsg("direito", paginas=1, tipo_documento="decisoes")
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


@pytest.mark.integration
def test_cjsg_factory():
    import juscraper as jus
    scraper = jus.scraper("tjto")
    assert isinstance(scraper, TJTOScraper)
    df = scraper.cjsg("direito", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty


if __name__ == "__main__":
    pytest.main([__file__])
