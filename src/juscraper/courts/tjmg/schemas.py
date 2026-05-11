"""Pydantic schemas for TJMG scraper endpoints.

Wired em :mod:`juscraper.courts.tjmg.client` via
:func:`juscraper.utils.params.apply_input_pipeline_search` (refs #93/#165).
A lista de campos bate byte-a-byte com a assinatura publica de
:meth:`TJMGScraper.cjsg` / :meth:`TJMGScraper.cjsg_download`.
"""
from __future__ import annotations

from typing import Literal

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, SearchBase


class InputCJSGTJMG(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for TJMG ``cjsg`` / ``cjsg_download``.

    Endpoint HTML com captcha numerico de 5 digitos decodificado via
    ``txtcaptcha``. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Apos a normalizacao, os kwargs que sobram
    caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtros de data herdados dos mixins.
    """

    pesquisar_por: Literal["ementa", "acordao"] = "ementa"
    order_by: Literal[0, 1, 2, "0", "1", "2"] = 2
    tamanho_pagina: Literal[10, 20, 50] = 10


class OutputCJSGTJMG(OutputCJSGBase, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJMGScraper.cjsg`.

    Reflete ``tjmg.parse.cjsg_parse``. TJMG nao entrega ``orgao_julgador``
    no HTML; extensoes internas (``processo_interno``, ``proc_ano``,
    ``proc_numero``) sao IDs do sistema interno do TJ.
    """

    processo_interno: str | None = None
    tipo_ato: str | None = None
    relator: str | None = None
    proc_ano: str | None = None
    proc_numero: str | None = None
