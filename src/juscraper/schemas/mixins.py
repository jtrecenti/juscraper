"""Mixins compartilhados extraidos por evidencia (refs #93).

A promocao para este modulo obedece a regra de generalizacao sob demanda do
#84: so mixin quando a evidencia concreta mostra que >= 2 tribunais usam o
mesmo conjunto de campos com o mesmo significado.

Atual:

- :class:`DataJulgamentoMixin` — filtro de Input (~13 tribunais).
- :class:`DataPublicacaoMixin` — filtro de Input (~11 tribunais).
- :class:`AutoChunkMixin` — flag de Input (familia eSAJ; cjsg + cjpg).
- :class:`OutputRelatoriaMixin` — colunas de Output (>= 10 parsers cjsg
  concretos).
- :class:`OutputDataPublicacaoMixin` — coluna de Output (>= 9 parsers).
"""
from __future__ import annotations

from datetime import date

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


class AutoChunkMixin(BaseModel):
    """Flag opcional ``auto_chunk`` para endpoints com teto de janela (issue #130).

    Default ``True``: quando o intervalo ``data_julgamento_*`` excede o teto
    do tribunal (eSAJ: 366 dias), o scraper divide internamente em janelas,
    baixa cada uma, concatena e deduplica. ``auto_chunk=False`` mantem o
    comportamento estrito (``ValueError`` em janelas longas) — util para
    validar input antes de submeter um job pesado.

    Tribunais que aceitam intervalos arbitrarios **nao devem herdar** deste
    mixin — ``extra='forbid'`` da classe concreta rejeita o flag e o usuario
    entende que a busca nao tem teto a contornar. Hoje so a familia eSAJ
    (cjsg em TJSP/TJAC/TJAL/TJAM/TJCE/TJMS, cjpg em TJSP) usa.
    """

    auto_chunk: bool = True


class OutputRelatoriaMixin(BaseModel):
    """Colunas de relatoria observaveis em parsers cjsg concretos.

    Presente em >= 10 parsers (eSAJ, TJBA, TJRN, TJRS, TJMG, TJPR, TJPA,
    TJRJ, TJMT, TJTO). ``extra='allow'`` da classe concreta cobre colunas
    auxiliares (``relator_id``, ``orgao_julgador_id``, etc.).
    """

    relator: str | None = None
    orgao_julgador: str | None = None


class OutputDataPublicacaoMixin(BaseModel):
    """Coluna de saida ``data_publicacao`` (parsers cjsg).

    Aceita ``date`` (parsers que convertem via ``pd.to_datetime(...).dt.date``)
    ou ``str`` (parsers que entregam ainda nao parseado). Convergir para
    ``date`` e meta de cada refactor individual do #84; ate la, ``date | str``
    reflete o estado real sem forcar conversao.
    """

    data_publicacao: date | str | None = None
