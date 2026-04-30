"""Pydantic schemas for TJRN scraper endpoints."""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputRelatoriaMixin, SearchBase


class InputCJSGTJRN(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRN ``cjsg``.

    Endpoint REST JSON (Elasticsearch). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Alias
    ``id_classe_judicial`` -> ``id_classe`` popado em ``client.cjsg``
    via :func:`pop_deprecated_alias` (refs #129).
    """

    numero_processo: str = ""
    id_classe: str = ""
    id_orgao_julgador: str = ""
    id_relator: str = ""
    id_colegiado: str = ""
    sistema: str = ""
    decisoes: str = ""
    jurisdicoes: str = ""
    grau: str = ""


class OutputCJSGTJRN(OutputCJSGBase, OutputRelatoriaMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRNScraper.cjsg`.

    Reflete ``tjrn.parse.cjsg_parse_manager`` apos renomeacao canonica
    (``classe_judicial`` -> ``classe``). ``data_publicacao`` nao e
    entregue pelo backend Elasticsearch.
    """

    classe: str | None = None
    colegiado: str | None = None
    tipo_decisao: str | None = None
    sistema: str | None = None
    sigiloso: bool | str | None = None
