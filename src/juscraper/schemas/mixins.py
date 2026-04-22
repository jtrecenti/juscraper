"""Mixins compartilhados extraidos por evidencia (refs #93).

A promocao para este modulo obedece a regra de generalizacao sob demanda do
#84: so mixin quando a evidencia concreta mostra que >= 2 tribunais usam o
mesmo conjunto de campos com o mesmo significado.

Atual:

- :class:`DataJulgamentoMixin` — ~13 tribunais suportam filtro de intervalo
  de data de julgamento.
- :class:`DataPublicacaoMixin` — ~11 tribunais (eSAJ puro + derivados com
  suporte: TJBA, TJES, TJMT, TJPA, TJSC, TJRS, etc.).
"""
from __future__ import annotations

from pydantic import BaseModel


class DataJulgamentoMixin(BaseModel):
    """Filtro opcional por intervalo de data de julgamento.

    Tribunais que nao suportam este filtro **nao devem herdar** deste mixin
    — ``extra="forbid"`` da classe concreta vai rejeitar
    ``data_julgamento_*`` corretamente, sinalizando ao usuario que a busca
    nao aceita o filtro.
    """

    data_julgamento_inicio: str | None = None
    data_julgamento_fim: str | None = None


class DataPublicacaoMixin(BaseModel):
    """Filtro opcional por intervalo de data de publicacao.

    Tribunais que nao suportam este filtro **nao devem herdar** deste mixin
    — ``extra="forbid"`` da classe concreta vai rejeitar ``data_publicacao_*``
    corretamente, sinalizando ao usuario que a busca nao aceita o filtro.
    """

    data_publicacao_inicio: str | None = None
    data_publicacao_fim: str | None = None
