"""Schemas pydantic do raspador do STM."""
from __future__ import annotations

from datetime import date
from typing import Literal

from ...schemas import OutputCJSGBase, SearchBase
from ...schemas.mixins import OutputDataPublicacaoMixin


class InputCJSGSTM(SearchBase):
    """Filtros aceitos por ``STMScraper.cjsg`` / ``cjsg_download``.

    ``campo`` é o seletor da caixa de busca do portal. Os demais filtros são
    os da coluna "Filtrar por" e casam com o valor exato que o portal exibe,
    em maiúsculas (``"APELAÇÃO"``, ``"CARLOS VUYK DE AQUINO"``).

    O portal filtra datas por intervalo só na pesquisa avançada, que usa
    outra sintaxe de consulta; por isso ``data_julgamento_*`` e
    ``data_publicacao_*`` não são aceitos e caem em ``extra="forbid"``.
    """

    campo: Literal["ementa", "inteiro_teor", "numero"] = "ementa"
    classe: str | None = None
    relator: str | None = None
    relator_acordao: str | None = None
    revisor: str | None = None
    assunto: str | None = None


class OutputCJSGSTM(OutputCJSGBase, OutputDataPublicacaoMixin):
    """Colunas de uma linha do DataFrame de ``STMScraper.cjsg``.

    Reflete ``stm.parse.cjsg_parse_manager``. Só ``processo``, ``classe``,
    ``relator`` e ``data_julgamento`` vêm em todo documento; os demais campos
    ficam vazios quando o portal não os publica.
    """

    id_documento: str | None = None
    classe: str | None = None
    relator: str | None = None
    relator_acordao: str | None = None
    revisor: str | None = None
    assunto: str | None = None
    data_autuacao: date | str | None = None
    url_inteiro_teor: str | None = None
