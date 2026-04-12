"""Integration tests for the TJRJ jurisprudence scraper."""
import pandas as pd
import pytest

import juscraper as jus


@pytest.mark.integration
def test_cjsg_busca_simples():
    tjrj = jus.scraper("tjrj")
    df = tjrj.cjsg(pesquisa="dano moral", ano_inicio=2024, ano_fim=2024, paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    for col in ("processo", "classe", "orgao_julgador", "relator", "ementa"):
        assert col in df.columns


@pytest.mark.integration
def test_cjsg_paginacao():
    tjrj = jus.scraper("tjrj")
    df1 = tjrj.cjsg(pesquisa="dano moral", ano_inicio=2024, ano_fim=2024, paginas=1)
    df2 = tjrj.cjsg(
        pesquisa="dano moral", ano_inicio=2024, ano_fim=2024, paginas=range(1, 3)
    )
    assert len(df2) > len(df1)
    assert set(df1["cod_documento"]) != set(df2["cod_documento"])


@pytest.mark.integration
def test_cjsg_download_parse_separados():
    tjrj = jus.scraper("tjrj")
    raw = tjrj.cjsg_download(
        pesquisa="dano moral", ano_inicio=2024, ano_fim=2024, paginas=1
    )
    assert isinstance(raw, list) and raw
    assert "DocumentosConsulta" in raw[0]
    df = tjrj.cjsg_parse(raw)
    assert not df.empty
    assert df["ementa"].str.len().max() > 0
