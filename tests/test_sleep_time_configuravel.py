"""O construtor aceita ``sleep_time``, a pausa entre as páginas de uma busca (refs #801).

TJAP, TJBA, TJES, TJMT, TJPA, TJPB e TJPE fixavam 1 s no download, e TJPR e
TJRS não pausavam. Que o valor chega ao ``time.sleep`` está em
``tests/test_contrato_paginas_explicitas.py`` para TJBA, TJES, TJPA, TJPB e
TJRS; aqui ficam os demais, de busca em vários passos.
"""
import pytest

import juscraper as jus


@pytest.mark.parametrize("sigla", ["tjap", "tjmt", "tjpe", "tjpr"])
def test_construtor_aceita_sleep_time(sigla):
    assert jus.scraper(sigla).sleep_time == 1.0
    assert jus.scraper(sigla, sleep_time=0.25).sleep_time == 0.25
