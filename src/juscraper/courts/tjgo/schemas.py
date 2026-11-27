"""Pydantic schemas for TJGO scraper endpoints.

Wired em :mod:`juscraper.courts.tjgo.client` via
:func:`juscraper.utils.params.apply_input_pipeline_search` (refs #93/#165).
A lista de campos bate byte-a-byte com a assinatura publica de
:meth:`TJGOScraper.cjsg` / :meth:`TJGOScraper.cjsg_download`.
"""
from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BeforeValidator, model_validator

from ...schemas import DataPublicacaoMixin, OutputCJSGBase, SearchBase, TamanhoPagina
from ...schemas.types import _coerce_id_filtro_unico

# Codigos do seletor "Orgao" (lista ``tipos`` de ``js/ConsultaJurisprudencia.js``
# do Projudi, nov/2026). ``"0"`` = todos. Usado tambem nas assinaturas de ``TJGOScraper``.
IdServentiaSubtipo = Literal[
    "0", "1", "2", "3", "6", "7", "8", "9", "10", "11", "12", "14", "20", "21", "22",
    "26", "27", "34", "35", "36", "37", "39", "41", "42", "43", "44", "45", "46",
    "47", "49", "58", "60", "61", "63", "64", "66", "67", "68", "69", "70", "71",
    "72", "81", "82", "83",
]

# Codigos do seletor "Orgao" por instancia (``servTipoId``) e area (``areaId``),
# da lista ``tipos`` de ``js/ConsultaJurisprudencia.js`` do Projudi (nov/2026).
# A instancia ``16`` (1o grau) saiu do seletor "Instancia": seus orgaos so
# aparecem com "Todas as instancias". Os orgaos das Turmas Recursais tem area
# ``3``, que o seletor "Area" nao oferece.
ORGAOS_POR_INSTANCIA_E_AREA: dict[tuple[str, str], frozenset[str]] = {
    ("151", "3"): frozenset({"6", "66"}),
    ("15", "1"): frozenset({"10", "14", "21", "22", "41", "70"}),
    ("15", "2"): frozenset({"10", "20", "22", "46", "71"}),
    ("16", "1"): frozenset({
        "1", "3", "7", "8", "9", "12", "26", "27", "34", "35", "36", "37", "42", "43",
        "45", "49", "58", "64", "68", "69", "72", "81", "82", "83",
    }),
    ("16", "2"): frozenset({"2", "3", "11", "39", "42", "44", "47", "60", "61", "63", "67"}),
}


class InputCJSGTJGO(SearchBase, DataPublicacaoMixin):
    """Accepted input for TJGO ``cjsg`` / ``cjsg_download``.

    Endpoint HTML Projudi. ``pesquisa`` aceita os aliases deprecados
    ``query`` / ``termo`` via :func:`juscraper.utils.params.normalize_pesquisa`,
    que roda *antes* deste modelo. Filtro de data de publicacao vem de
    :class:`DataPublicacaoMixin`; o backend Projudi nao expoe filtro de data
    de julgamento — passar ``data_julgamento_inicio`` / ``data_julgamento_fim``
    levanta :class:`TypeError` via ``extra="forbid"`` herdado de
    :class:`SearchBase`.

    A API publica do TJGO aceita datas em ISO (``YYYY-MM-DD``); o client
    converte para o formato BR (``DD/MM/YYYY``) esperado pelo Projudi via
    ``_br_date`` antes do POST.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"

    # Opcoes do seletor "Instancia" do formulario do Projudi (nov/2026): ``15``
    # Tribunal, ``151`` Turma de Uniformizacao / Turmas Recursais, ``0`` todas.
    # Mais ``1``, deprecado (ver ``_resolver_id_instancia`` no client).
    id_instancia: Literal[0, 15, 151, 1, "0", "15", "151", "1"] = 0
    id_area: Literal[0, 1, 2, "0", "1", "2"] = 0
    # Inteiros sao aceitos e viram string.
    id_serventia_subtipo: Annotated[IdServentiaSubtipo, BeforeValidator(_coerce_id_filtro_unico)] = "0"
    numero_processo: str | None = None
    tamanho_pagina: TamanhoPagina = 10

    @model_validator(mode="after")
    def _combinacao_do_formulario(self) -> InputCJSGTJGO:
        """Recusa combinacoes que o formulario do Projudi nao monta.

        Replica ``inicializarAreas``/``atualizarAreas`` (com instancia ``151`` so
        ha a area ``0``) e ``filtrarOpcoes`` (o seletor "Orgao" so lista os
        orgaos da instancia e da area escolhidas; ``0`` nao filtra). ``1``,
        deprecado e fora do formulario, fica sem conferencia.
        """
        instancia, area = str(self.id_instancia), str(self.id_area)
        orgao = self.id_serventia_subtipo
        if instancia == "151" and area != "0":
            raise ValueError(
                f"id_area={area} nao existe com id_instancia=151: o formulario do Projudi "
                "so oferece a area 0 (todas) nas Turmas Recursais."
            )
        if orgao == "0" or instancia == "1":
            return self
        aceitos = {
            codigo
            for (tipo, area_orgao), codigos in ORGAOS_POR_INSTANCIA_E_AREA.items()
            if instancia in ("0", tipo) and area in ("0", area_orgao)
            for codigo in codigos
        }
        if orgao not in aceitos:
            raise ValueError(
                f"id_serventia_subtipo={orgao!r} nao e oferecido pelo formulario do Projudi "
                f"com id_instancia={instancia} e id_area={area}. "
                f"Use 0 (todos) ou um de: {', '.join(sorted(aceitos, key=int))}."
            )
        return self


class OutputCJSGTJGO(OutputCJSGBase):
    """Colunas observaveis em uma linha do DataFrame de :meth:`TJGOScraper.cjsg`.

    O parser do TJGO (``src/juscraper/courts/tjgo/parse.py``) entrega o
    conteudo do documento na coluna ``texto``, nao em ``ementa`` — diferente
    dos demais cjsg. ``OutputCJSGBase.ementa`` ja e Optional, entao o TJGO
    apenas nao preenche ``ementa``. No HTML atual (nov/2026) ``tipo_ato`` vem
    vazio, e ``data_publicacao`` vem do paragrafo rotulado "Julgado em ...",
    o mesmo campo que o formato antigo rotulava "Publicado em ...".
    """

    id_arquivo: str | None = None
    serventia: str | None = None
    relator: str | None = None
    tipo_ato: str | None = None
    data_publicacao: str | None = None
    texto: str | None = None
