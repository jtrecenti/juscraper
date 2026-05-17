"""Helpers compartilhados pelos contratos cjsg do TJPR.

A ``home`` GET é idêntica em ambos ``test_cjsg_contract.py`` e
``test_cjsg_filters_contract.py``; promovida para evitar drift. Os
helpers de POST de busca divergem em assinatura (sample fixo + matcher
dinâmico vs sample dinâmico + matcher de página) e ficam locais a cada
arquivo.
"""
from __future__ import annotations

import responses

from juscraper.courts.tjpr.download import BASE_URL as HOME_URL
from juscraper.courts.tjpr.download import SEARCH_URL
from tests._helpers import load_sample

__all__ = ["HOME_URL", "SEARCH_URL", "add_home"]


def add_home() -> None:
    responses.add(
        responses.GET,
        HOME_URL,
        body=load_sample("tjpr", "cjsg/home.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )
