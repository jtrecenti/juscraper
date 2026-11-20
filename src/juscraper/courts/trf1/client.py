"""Raspador do Tribunal Regional Federal da 1ª Região (TRF1).

Consulta processual pública do PJe do TRF1 (1º grau). Em novembro de 2026 o
endereço JSF (``pje1g-consultapublica.trf1.jus.br/consultapublica/ConsultaPublica/listView.seam``)
passou a responder 404, e a raiz ``.../consultapublica/ConsultaPublica/``
passou a servir a aplicação Angular que o TRF3 já usava, sobre a mesma API
JSON, em ``.../consultapublica/api``. O fluxo fica em
:class:`juscraper.courts._pje_api.base.PJeAPIScraper`. Ao contrário da do
TRF3, a aplicação do TRF1 não manda o cabeçalho ``x-pagina-origem`` e
respondeu sem bloqueio a requisições do ``requests`` de IP de datacenter.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from ...core.http import RequestPolicy
from ...schemas import CnjInputBase
from .._pje_api.base import PJeAPIScraper
from .._pje_api.download import AplicacaoPJe
from .schemas import InputCpopgTRF1

#: Raiz da API da consulta pública de 1º grau.
API_URL_1G = "https://pje1g-consultapublica.trf1.jus.br/consultapublica/api"

APLICACAO_1G = AplicacaoPJe("TRF1", API_URL_1G)


class TRF1Scraper(PJeAPIScraper):
    """Raspador do TRF1: consulta pública do PJe (1º grau).

    Perfis HTTP ajustáveis com ``politica=``: ``"api"`` (busca e detalhe,
    timeout de leitura de 60 s) e ``"documento"`` (PDF das peças, timeout de
    leitura de 120 s), sem nova tentativa em timeout ou erro de conexão.
    """

    TRIBUNAL_NAME: str = APLICACAO_1G.tribunal
    APLICACAO_1G: ClassVar[AplicacaoPJe] = APLICACAO_1G
    INPUT_CPOPG: type[CnjInputBase] = InputCpopgTRF1
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "api": RequestPolicy(timeout=(10.0, 60.0), expect_json=True),
        "documento": RequestPolicy(timeout=(10.0, 120.0)),
    }
