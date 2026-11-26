"""Pydantic schemas for TJRN scraper endpoints."""
from __future__ import annotations

from typing import ClassVar, Literal

from ...schemas import DataJulgamentoMixin, OutputCJSGBase, OutputDataPublicacaoMixin, OutputRelatoriaMixin, SearchBase

# Campos de texto do portal onde ``pesquisa`` pode ir.
BuscarEm = Literal["ementa", "inteiro_teor"]


class InputCJSGTJRN(SearchBase, DataJulgamentoMixin):
    """Accepted input for TJRN ``cjsg`` / ``cjsg_download``.

    Wired em :meth:`juscraper.courts.tjrn.client.TJRNScraper.cjsg_download`
    desde o #183 — kwargs desconhecidos viram :class:`TypeError` em ambos
    ``cjsg`` e ``cjsg_download``. ``cjsg`` e wrapper trivial
    (``download → parse``).

    Endpoint REST JSON (Elasticsearch). ``pesquisa`` aceita os aliases
    deprecados ``query`` / ``termo`` via
    :func:`juscraper.utils.params.normalize_pesquisa`, que roda *antes*
    deste modelo. Datas de julgamento aceitam os aliases
    ``data_inicio``/``data_fim`` via
    :func:`juscraper.utils.params.normalize_datas` (``data_publicacao_*``
    nao e suportado pelo backend e fica fora do schema). Filtro de data
    de julgamento herdado de :class:`DataJulgamentoMixin`.

    ``BACKEND_DATE_FORMAT`` (``YYYY-MM-DD``) e so o formato interno do
    pipeline. O portal espera ``DD-MM-YYYY`` com hifens: a conversao fica em
    :func:`juscraper.courts.tjrn.client._to_tjrn_date`, porque o backend
    ignora datas com barras ou em ISO e devolve resultados sem filtro.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    numero_processo: str | None = None
    id_classe: str | None = None
    id_orgao_julgador: str | None = None
    id_relator: str | None = None
    id_colegiado: str | None = None
    sistema: str | None = None
    # Valores do seletor "Decisoes" do portal (``field-decisao.js``), que o backend
    # compara com ``tipo_teor``: "Decisão" sao as monocraticas, "Acórdão" as
    # colegiadas e "Sentença" as de 1o grau. Vazio (ou ``None``) busca todas.
    decisoes: Literal["", "Decisão", "Acórdão", "Sentença"] | None = None
    # Valores do seletor "Jurisdicoes" do portal (``field-jurisdicao.js``): "TJ"
    # (Tribunal de Justica) e "TR" (Turmas Recursais e TUJ). Vazio (ou ``None``)
    # busca todas. Os nomes por extenso fazem o portal responder 502/503.
    jurisdicoes: Literal["", "TJ", "TR"] | None = None
    grau: str | None = None
    buscar_em: BuscarEm = "ementa"


class OutputCJSGTJRN(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJRNScraper.cjsg`.

    Reflete ``tjrn.parse.cjsg_parse_manager`` apos renomeacao canonica
    (``classe_judicial`` -> ``classe``). ``data_publicacao`` vem de
    ``dt_publicacao`` do backend Elasticsearch, convertida para ``date``.
    ``relator`` vem de ``magistrado`` (na sentenca, o juiz de 1o grau) e
    ``tipo_decisao`` de ``tipo_teor``: ``"Acórdão"``, ``"Decisão"``
    (monocratica) ou ``"Sentença"``.
    """

    classe: str | None = None
    colegiado: str | None = None
    tipo_decisao: str | None = None
    sistema: str | None = None
    sigiloso: bool | str | None = None
