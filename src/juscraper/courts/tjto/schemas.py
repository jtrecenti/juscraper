"""Pydantic schemas for TJTO scraper endpoints.

``cpopg`` e ``cposg`` do TJTO sao stubs ``NotImplementedError`` no client
atual — por isso nao ganham schemas de Input/Output aqui.
"""
from __future__ import annotations

from datetime import date
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputRelatoriaMixin, SearchBase


class InputCJSGTJTO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJTO ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjto.client.TJTOScraper.cjsg_download`
    — kwargs desconhecidos viram :class:`TypeError` em ambos ``cjsg`` e
    ``cjsg_download``. ``cjsg`` e wrapper trivial (``download → parse``).

    Endpoint HTML (``jurisprudencia.tjto.jus.br/consulta.php``). ``pesquisa``
    aceita os aliases deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes* deste
    modelo. Datas aceitam os aliases ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas`. Filtro de data de
    julgamento herdado de :class:`DataJulgamentoMixin`. Backend espera
    ``DD/MM/YYYY`` (convertido por ``to_br_date`` em
    :func:`juscraper.courts.tjto.download.build_cjsg_payload`).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%d/%m/%Y"

    tipo_documento: str = "acordaos"
    ordenacao: str = "DESC"
    numero_processo: str = ""
    soementa: bool = False


class _OutputCJSGTJTOBase(OutputCJSGBase, OutputRelatoriaMixin):
    """Colunas compartilhadas entre ``cjsg`` e ``cjpg`` do TJTO.

    Reflete ``tjto.parse.cjsg_parse_manager``. O parser nao extrai ementa
    na listagem — usa-se :meth:`TJTOScraper.cjsg_ementa` com ``uuid`` para
    buscar a ementa de cada acordao individualmente.
    """

    uuid: str | None = None
    classe: str | None = None
    tipo_julgamento: str | None = None
    assunto: str | None = None
    competencia: str | None = None
    data_autuacao: date | str | None = None
    processo_link: str | None = None


class OutputCJSGTJTO(_OutputCJSGTJTOBase):
    """Output do cjsg (2o grau) do TJTO."""


class InputCJPGTJTO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJTO ``cjpg`` / ``cjpg_download``.

    A assinatura de ``cjpg`` e identica a de ``cjsg`` — a unica diferenca
    interna e ``instancia='1'`` em vez de ``'2'`` no download manager.
    Filtro de data de julgamento herdado de :class:`DataJulgamentoMixin`.
    Backend espera ``DD/MM/YYYY`` (convertido por ``to_br_date`` em
    :func:`juscraper.courts.tjto.download.build_cjsg_payload`).
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%d/%m/%Y"

    tipo_documento: str = "acordaos"
    ordenacao: str = "DESC"
    numero_processo: str = ""
    soementa: bool = False


class OutputCJPGTJTO(_OutputCJSGTJTOBase):
    """Output do cjpg (1o grau) do TJTO. Mesmas colunas do cjsg — so muda ``instancia=1``."""


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
