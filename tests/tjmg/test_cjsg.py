"""Integration tests for the TJMG jurisprudence scraper."""
import pandas as pd
import pytest

import juscraper as jus

pytest.importorskip(
    "txtcaptcha",
    reason=(
        "TJMG hits a numeric image captcha solved via txtcaptcha "
        '(extra opcional `[tjmg]`; instale com `uv pip install -e ".[tjmg]"`).'
    ),
)


@pytest.mark.integration
def test_cjsg_busca_simples():
    tjmg = jus.scraper("tjmg")
    df = tjmg.cjsg(
        pesquisa="dano moral presumido",
        paginas=1,
        data_julgamento_inicio="2025-01-01",
        data_julgamento_fim="2025-03-31",
    )
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    for col in ("processo", "relator", "tipo_ato", "ementa", "data_julgamento"):
        assert col in df.columns


@pytest.mark.integration
def test_cjsg_paginacao():
    tjmg = jus.scraper("tjmg")
    df1 = tjmg.cjsg(
        pesquisa="dano moral presumido",
        paginas=1,
        data_julgamento_inicio="2025-01-01",
        data_julgamento_fim="2025-03-31",
    )
    df2 = tjmg.cjsg(
        pesquisa="dano moral presumido",
        paginas=range(1, 3),
        data_julgamento_inicio="2025-01-01",
        data_julgamento_fim="2025-03-31",
    )
    assert len(df2) > len(df1)
    extra = set(df2["processo"]) - set(df1["processo"])
    assert extra


@pytest.mark.integration
def test_cjsg_download_parse_separados():
    tjmg = jus.scraper("tjmg")
    raw = tjmg.cjsg_download(
        pesquisa="dano moral presumido",
        paginas=1,
        data_julgamento_inicio="2025-01-01",
        data_julgamento_fim="2025-03-31",
    )
    assert isinstance(raw, list) and raw
    assert "caixa_processo" in raw[0]
    df = tjmg.cjsg_parse(raw)
    assert not df.empty
    assert df["ementa"].str.len().max() > 0
