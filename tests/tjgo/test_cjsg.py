"""Integration tests for the TJGO jurisprudence scraper."""
import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
def test_cjsg_busca_simples():
    tjgo = jus.scraper("tjgo")
    df = tjgo.cjsg(pesquisa="dano moral", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    for col in ("processo", "serventia", "relator", "tipo_ato", "texto"):
        assert col in df.columns


@pytest.mark.integration
def test_cjsg_paginacao():
    tjgo = jus.scraper("tjgo")
    df1 = tjgo.cjsg(pesquisa="dano moral", paginas=1)
    df2 = tjgo.cjsg(pesquisa="dano moral", paginas=range(1, 3))
    assert len(df2) > len(df1)
    # Second page must contain processos not in the first
    extra = set(df2["processo"]) - set(df1["processo"])
    assert extra


@pytest.mark.integration
def test_cjsg_download_parse_separados():
    tjgo = jus.scraper("tjgo")
    raw = tjgo.cjsg_download(pesquisa="dano moral", paginas=1)
    assert isinstance(raw, list) and raw
    assert 'search-result' in raw[0]
    df = tjgo.cjsg_parse(raw)
    assert not df.empty
    assert df["texto"].str.len().max() > 0
