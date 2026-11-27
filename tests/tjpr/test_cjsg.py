import pandas as pd
import pytest
from bs4 import BeautifulSoup

from juscraper.courts.tjpr.client import TJPRScraper


@pytest.mark.integration
def test_cjsg_download_and_parse():
    scraper = TJPRScraper()
    htmls = scraper.cjsg_download(pesquisa="direito civil", paginas=1)
    assert isinstance(htmls, list)
    assert len(htmls) == 1
    html = htmls[0]
    assert "html" in html.lower() or "DOCTYPE" in html[:100]
    df = scraper.cjsg_parse(htmls)
    assert not df.empty, (
        "DataFrame vazio; tabelas no HTML: "
        f"{len(BeautifulSoup(html, 'html.parser').find_all('table'))}. "
        f"Início do HTML:\n{html[:10000]}"
    )
    for col in ["processo", "orgao_julgador", "relator", "data_julgamento", "ementa"]:
        assert col in df.columns
    assert df["ementa"].str.len().max() > 0


@pytest.mark.integration
def test_cjsg_interface():
    scraper = TJPRScraper()
    df = scraper.cjsg(pesquisa="direito civil", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert not df.empty, "DataFrame vazio na interface cjsg."
    assert "ementa" in df.columns
    assert df["ementa"].str.len().max() > 0
