"""Pydantic schemas for TJRN scraper endpoints.

Ainda nao wired em :mod:`juscraper.courts.tjrn.client` — este arquivo e
documentacao executavel da API publica ate o TJRN ser refatorado para o
pipeline canonico da #93. A lista de campos bate byte-a-byte com a
assinatura publica de :meth:`TJRNScraper.cjsg`.
"""
from __future__ import annotations

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, SearchBase


class InputCJSGTJRN(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRN ``cjsg``.

    Endpoint REST JSON (Elasticsearch). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Filtro de data
    de julgamento herdado de :class:`DataJulgamentoMixin`.
    """

    nr_processo: str = ""
    id_classe_judicial: str = ""
    id_orgao_julgador: str = ""
    id_relator: str = ""
    id_colegiado: str = ""
    sistema: str = ""
    decisoes: str = ""
    jurisdicoes: str = ""
    grau: str = ""


class OutputCJSGTJRN(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRNScraper.cjsg`.

    Provisorio — revisar quando samples forem capturados (refs #113).
    """
