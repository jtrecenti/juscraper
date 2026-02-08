import pytest
from juscraper.courts.tjdft.client import TJDFTScraper


@pytest.mark.integration
def test_cjsg_standalone():
    scraper = TJDFTScraper()
    df = scraper.cjsg(query='direito penal', paginas=1)
    print(df.head())
    assert not df.empty
    assert "ementa" in df.columns
    assert "processo" in df.columns


if __name__ == "__main__":
    test_cjsg_standalone()
