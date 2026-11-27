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


@pytest.mark.integration
def test_cjsg_segue_a_busca_categorizada():
    """Com acórdãos de repetitivos no resultado, o portal responde com a busca categorizada."""
    df = jus.scraper("tjmg").cjsg(
        pesquisa="usucapiao",
        paginas=1,
        data_julgamento_inicio="2025-01-01",
        data_julgamento_fim="2025-12-31",
    )
    assert len(df) > 10  # a página 1 de cada lista: repetitivos e demais acórdãos
    assert df["processo"].is_unique


@pytest.mark.integration
def test_cjsg_download_sem_filtro_de_data_levanta_muitos_resultados():
    """Busca ampla sem filtro de data: o portal responde "muitos resultados".

    Em 15/11/2026 essa busca voltava com o erro do banco (``ORA-20000``); em
    26/11/2026, com "muitos resultados". O caminho do erro do banco segue
    coberto offline pelo sample ``erro_ora.html``
    (``test_cjsg_busca_sem_lista_contract.py``).
    """
    with pytest.raises(ValueError, match="muitos resultados"):
        jus.scraper("tjmg").cjsg_download(pesquisa="dano moral", paginas=1)
