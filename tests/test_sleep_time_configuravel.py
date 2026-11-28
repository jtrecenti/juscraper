"""A pausa entre páginas é ``sleep_time``, do construtor, em todo raspador paginado.

TJAP, TJBA, TJES, TJMT, TJPA, TJPB e TJPE fixavam 1 s no download, e TJPR e
TJRS não pausavam; os nove passam a receber ``sleep_time`` (default 1 s), como
os demais (refs #801).
"""
import pytest

import juscraper as jus


@pytest.mark.parametrize("sigla", ["tjap", "tjba", "tjes", "tjmt", "tjpa", "tjpb", "tjpe", "tjpr", "tjrs"])
def test_construtor_aceita_sleep_time(sigla):
    assert jus.scraper(sigla).sleep_time == 1.0
    assert jus.scraper(sigla, sleep_time=0.25).sleep_time == 0.25
