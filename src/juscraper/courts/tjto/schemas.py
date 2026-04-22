"""Pydantic schemas for TJTO scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjto.client` — este arquivo e
documentacao executavel da API publica ate o TJTO ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica dos metodos publicos de :class:`TJTOScraper`.

``cpopg`` e ``cposg`` do TJTO sao stubs ``NotImplementedError`` no client
atual — por isso nao ganham schemas de Input/Output aqui.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJTO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJTO ``cjsg`` / ``cjsg_download``.

    Endpoint HTML (``jurisprudencia.tjto.jus.br/consulta.php``). ``pesquisa``
    aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes* deste
    modelo. Datas aceitam os aliases ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas`. Filtro de data de
    julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    tipo_documento: str = "acordaos"
    ordenacao: str = "DESC"
    numero_processo: str = ""
    soementa: bool = False


class OutputCJSGTJTO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJTOScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """


class InputCJPGTJTO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJTO ``cjpg`` / ``cjpg_download``.

    A assinatura de ``cjpg`` e identica a de ``cjsg`` — a unica diferenca
    interna e ``instancia='1'`` em vez de ``'2'`` no download manager.
    Filtro de data de julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    tipo_documento: str = "acordaos"
    ordenacao: str = "DESC"
    numero_processo: str = ""
    soementa: bool = False


class OutputCJPGTJTO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJTOScraper.cjpg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """


class InputCjsgEmentaTJTO(BaseModel):
    """Accepted input for :meth:`TJTOScraper.cjsg_ementa`.

    Metodo busca o texto da ementa de um documento especifico pelo UUID
    retornado na coluna ``uuid`` dos resultados de ``cjsg`` / ``cjpg``.
    """

    uuid: str

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )
