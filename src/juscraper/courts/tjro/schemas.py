"""Pydantic schemas for TJRO scraper endpoints."""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRO(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRO ``cjsg`` / ``cjsg_download``.

    Endpoint Elasticsearch do JURIS (juris-back.tjro.jus.br) com paginacao
    por offset. ``pesquisa`` aceita os aliases deprecados ``query`` /
    ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`, que
    roda *antes* deste modelo. Aliases ``magistrado`` -> ``relator`` e
    ``classe_judicial`` -> ``classe`` sao popados em ``client.cjsg`` via
    :func:`pop_deprecated_alias` (refs #129). Filtro de data de julgamento
    herdado de :class:`DataJulgamentoMixin`.
    """

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
