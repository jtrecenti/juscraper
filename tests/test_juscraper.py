from juscraper import scraper


def test_scraper_factory_is_callable():
    assert callable(scraper)
