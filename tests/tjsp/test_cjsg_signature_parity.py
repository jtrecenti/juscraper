"""Garante que o override raso de TJSPScraper.cjsg nao drift da base eSAJ.

O override em ``src/juscraper/courts/tjsp/client.py`` so faz
``return super().cjsg(...)`` e existe apenas para ancorar uma docstring
TJSP-especifica (ja que ``InputCJSGTJSP`` difere de ``InputCJSGEsajPuro``).
Quando ``EsajSearchScraper.cjsg`` ganha um parametro novo, este teste
falha e o override precisa ser atualizado para refletir a base — caso
contrario o parametro novo seria silenciosamente engolido por ``**kwargs``
ou geraria ``TypeError`` confuso.
"""
from __future__ import annotations

import inspect

from juscraper.courts._esaj.base import EsajSearchScraper
from juscraper.courts.tjsp.client import TJSPScraper


def test_tjsp_cjsg_signature_matches_base():
    base_sig = inspect.signature(EsajSearchScraper.cjsg)
    tjsp_sig = inspect.signature(TJSPScraper.cjsg)
    assert tjsp_sig.parameters.keys() == base_sig.parameters.keys(), (
        "TJSPScraper.cjsg desincronizou de EsajSearchScraper.cjsg.\n"
        f"  base:  {list(base_sig.parameters.keys())}\n"
        f"  tjsp:  {list(tjsp_sig.parameters.keys())}\n"
        "Atualize o override em tjsp/client.py para refletir a base "
        "(ou remova o override e mova a docstring para outro lugar)."
    )
