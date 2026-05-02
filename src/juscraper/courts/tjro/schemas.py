"""Pydantic schemas for TJRO scraper endpoints."""
from __future__ import annotations

from typing import ClassVar

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRO ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjro.client.TJROScraper.cjsg_download`
    desde o #183 — kwargs desconhecidos viram :class:`TypeError` em ambos
    ``cjsg`` e ``cjsg_download``. ``cjsg`` e wrapper trivial
    (``download → parse``).

    Endpoint Elasticsearch do JURIS (juris-back.tjro.jus.br) com paginacao
    por offset. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Apos a normalizacao, os kwargs que sobram
    caem aqui e sao rejeitados por ``extra="forbid"`` herdado de
    :class:`SearchBase`. Filtro de data de julgamento herdado de
    :class:`DataJulgamentoMixin`. Backend espera ``YYYY-MM-DD``.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    tipo: list | None = None
    numero_processo: str = ""
    relator: str = ""
    orgao_julgador: int | str = ""
    orgao_julgador_colegiado: int | str = ""
    classe: str = ""
    instancia: list | None = None
    termo_exato: bool = False


class OutputCJSGTJRO(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJROScraper.cjsg`.

    Reflete ``tjro.parse.cjsg_parse_manager`` apos renomeacao canonica
    (``classe_judicial`` -> ``classe``).
    """

    tipo: str | None = None
    classe: str | None = None
    orgao_julgador_colegiado: str | None = None
    assunto: str | None = None
    grau_jurisdicao: str | None = None
    sistema_origem: str | None = None
