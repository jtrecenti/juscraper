"""Instalações da consulta pública do PJe do TRF3 (API JSON).

A consulta pública do TRF3 é uma aplicação Angular em
``pje1g-consultapublica.trf3.jus.br`` (1º grau) e
``pje2g-consultapublica.trf3.jus.br`` (2º grau), que consome a API JSON
descrita em :mod:`juscraper.courts._pje_api.download`. O endereço antigo
(``.../pje/ConsultaPublica/listView.seam``) redirecionava para ela; a situação
do 1º grau em 15/11/2026 está na docstring de
:meth:`juscraper.courts.trf3.client.TRF3Scraper.cpopg`. A aplicação manda o
cabeçalho ``x-pagina-origem`` em toda chamada, e o Akamai na frente do portal
segura sem resposta as requisições sem TLS de navegador, por isso a sessão usa
o transporte de :mod:`._tls`.
"""
from __future__ import annotations

import requests

from .._pje_api.download import AplicacaoPJe
from .._pje_api.download import guarda_akamai as _guarda_akamai

#: Sigla usada nas mensagens de erro e de log.
TRIBUNAL = "TRF3"

BASE_URL_1G = "https://pje1g-consultapublica.trf3.jus.br"
BASE_URL_2G = "https://pje2g-consultapublica.trf3.jus.br"

APLICACAO_1G = AplicacaoPJe(TRIBUNAL, BASE_URL_1G, origem_url=BASE_URL_1G)
APLICACAO_2G = AplicacaoPJe(TRIBUNAL, BASE_URL_2G, origem_url=BASE_URL_2G)


def guarda_akamai(resp: requests.Response) -> None:
    """Levanta :class:`~juscraper.core.exceptions.BotChallengeBlockedError` no 403 do Akamai do TRF3.

    Usada pelo ``cjsg``; a consulta processual usa a guarda da família.
    """
    _guarda_akamai(resp, TRIBUNAL)
