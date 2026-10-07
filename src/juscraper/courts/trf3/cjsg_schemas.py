"""Schemas pydantic do ``cjsg`` do TRF3 (busca de jurisprudência).

Ficam fora de um ``schemas.py`` do tribunal porque a busca de jurisprudência
(``web.trf3.jus.br/jurisprudencia``) é um sistema separado da consulta
processual do PJe, com contrato e ciclo de mudança próprios.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from ...schemas import DataJulgamentoMixin, DataPublicacaoMixin, OutputCJSGBase, SearchBase
from ...schemas.mixins import OutputDataPublicacaoMixin, OutputRelatoriaMixin

BaseCJSGTRF3 = Literal[
    "acordaos",
    "turmas_recursais",
    "monocraticas",
    "monocraticas_turmas_recursais",
]
"""Bases de pesquisa do portal. Cada valor corresponde a um conjunto de resultados.

* ``acordaos``: acórdãos do TRF3 (aba "TRF3" do portal).
* ``turmas_recursais``: acórdãos das Turmas Recursais dos JEFs.
* ``monocraticas``: decisões monocráticas do TRF3.
* ``monocraticas_turmas_recursais``: decisões monocráticas das Turmas Recursais.

As duas últimas saem da mesma aba ("Monocráticas") e se distinguem pelas caixas
"TRF3" e "Recursal (JEF)". Medido no portal: com as duas marcadas, ou nenhuma, o
resultado é o mesmo da caixa "TRF3" sozinha, e não a união. Por isso cada
origem é uma base, e não um filtro combinável.
"""

#: Filtros que o formulário da aba "Monocráticas" não tem. O servidor ignoraria
#: o campo e devolveria resultado sem o filtro pedido.
FILTROS_SEM_MONOCRATICAS: tuple[str, ...] = ("orgao_julgador", "ementa", "indexacao")

#: Filtros que, sozinhos, já contam como critério de pesquisa no formulário.
_CRITERIOS = (
    "numero_processo",
    "relator",
    "classe",
    "orgao_julgador",
    "ementa",
    "indexacao",
    "data_julgamento_inicio",
    "data_publicacao_inicio",
)


class InputCJSGTRF3(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    """Accepted input for :meth:`TRF3Scraper.cjsg` / ``cjsg_download``.

    O formulário tem um só par de datas e um seletor ``data_tipo``
    (publicação ou julgamento); por isso ``data_julgamento_*`` e
    ``data_publicacao_*`` não podem vir juntos. Nas bases de monocráticas, a
    data de julgamento é a data da decisão.

    ``relator``, ``classe`` e ``orgao_julgador`` são texto, não IDs: o portal
    ignora o ID do dropdown e pesquisa o texto nos campos indexados
    (``relator_t``/``relator_acordao_t``, ``classe_t`` e o órgão julgador).

    ``pesquisa`` pode ser vazia quando outro critério (número, filtro ou datas)
    for informado; sem nenhum critério o portal recusa a busca. Essas regras de
    combinação ficam em :func:`validar_combinacoes`, chamada pelo client depois
    do modelo.
    """

    BACKEND_DATE_FORMAT: ClassVar[str] = "%d/%m/%Y"

    base: BaseCJSGTRF3 = "acordaos"
    numero_processo: str | None = None
    relator: str | None = None
    classe: str | None = None
    orgao_julgador: str | None = None
    ementa: str | None = None
    indexacao: str | None = None
    tamanho_pagina: Literal[10, 30, 50] = 10


def validar_combinacoes(inp: InputCJSGTRF3) -> None:
    """Rejeita combinações que o formulário do portal não consegue expressar.

    Roda depois do pydantic (o modelo já resolveu aliases e coagiu as datas) e
    antes de qualquer requisição. Levanta :class:`ValueError` simples, e não
    ``ValidationError``, porque o problema é a combinação de campos válidos.

    Raises:
        ValueError: Datas de julgamento e de publicação juntas; filtro que a
            base de monocráticas não tem; nenhum critério de pesquisa.
    """
    tem_julgamento = bool(inp.data_julgamento_inicio or inp.data_julgamento_fim)
    tem_publicacao = bool(inp.data_publicacao_inicio or inp.data_publicacao_fim)
    if tem_julgamento and tem_publicacao:
        raise ValueError(
            "TRF3 cjsg: o formulário filtra por um só tipo de data. Passe "
            "data_julgamento_* ou data_publicacao_*, não os dois."
        )
    if inp.base.startswith("monocraticas"):
        recusados = [nome for nome in FILTROS_SEM_MONOCRATICAS if getattr(inp, nome)]
        if recusados:
            raise ValueError(
                f"TRF3 cjsg: a base {inp.base!r} não aceita o(s) filtro(s) "
                f"{', '.join(recusados)}; o formulário de monocráticas não tem esses campos."
            )
    if not (inp.pesquisa or "").strip() and not any(getattr(inp, nome) for nome in _CRITERIOS):
        raise ValueError(
            "TRF3 cjsg: informe pesquisa ou ao menos um filtro "
            "(numero_processo, relator, classe, orgao_julgador, ementa, indexacao ou datas)."
        )


class OutputCJSGTRF3(OutputCJSGBase, OutputRelatoriaMixin, OutputDataPublicacaoMixin):
    """Colunas observáveis em uma linha do DataFrame de :meth:`TRF3Scraper.cjsg`.

    Reflete ``trf3.cjsg_parse.cjsg_parse_manager``. Nas bases de monocráticas,
    ``ementa`` traz o texto da decisão (decisão monocrática não tem ementa) e
    ``orgao_julgador`` vem vazio. ``url_inteiro_teor`` só existe em acórdãos
    (TRF3 e Turmas Recursais).
    """

    classe: str | None = None
    relator_acordao: str | None = None
    meio_publicacao: str | None = None
    inteiro_teor: str | None = None
    url_inteiro_teor: str | None = None
    base: str | None = None
