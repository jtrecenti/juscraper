"""Mixins compartilhados extraidos por evidencia (refs #93).

A promocao para este modulo obedece a regra de generalizacao sob demanda do
#84: so mixin quando a evidencia concreta mostra que >= 2 tribunais usam o
mesmo conjunto de campos com o mesmo significado.

Atual:

- :class:`PaginasMixin` — contrato unico de ``paginas``
  (``int | list[int] | range | None``) usado por :class:`SearchBase` (cjsg/cjpg
  de todos os tribunais) e por :class:`InputListarProcessosDataJud`. DataJud
  nao tem ``pesquisa``, entao herda direto o mixin em vez de :class:`SearchBase`.
- :class:`DataJulgamentoMixin` — filtro de Input (~13 tribunais).
- :class:`DataPublicacaoMixin` — filtro de Input (~11 tribunais).
- :class:`AutoChunkMixin` — flag de Input (familia eSAJ; cjsg + cjpg).
- :class:`CountOnlyMixin` — flag de Input que muda o tipo de retorno para
  ``int`` (familia eSAJ cjsg + TJSP cjpg). Refs #92.
- :class:`OutputRelatoriaMixin` — colunas de Output (>= 10 parsers cjsg
  concretos).
- :class:`OutputDataPublicacaoMixin` — coluna de Output (>= 9 parsers).
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class PaginasMixin(BaseModel):
    """Contrato unico de ``paginas`` (refs #118).

    ``paginas`` e **1-based em todos os raspadores** — ``paginas=3`` equivale
    a ``range(1, 4)`` e baixa as paginas 1, 2 e 3. ``paginas=0`` e invalido.
    ``None`` (default) significa "todas as paginas disponiveis" — o scraper
    consulta o backend para descobrir o total. Runtime normaliza
    ``int`` -> ``range`` em :func:`juscraper.utils.params.normalize_paginas`
    antes do pydantic, mas o schema aceita as 4 formas para refletir a API
    publica.

    Schemas concretos **nao devem redeclarar** ``paginas`` — qualquer
    divergencia por tribunal vira bug a ser corrigido, nao particularidade
    a ser documentada. ``arbitrary_types_allowed=True`` e necessario porque
    ``range`` nao e um tipo nativo do pydantic.
    """

    paginas: int | list[int] | range | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)


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

    Nota: o flag ``auto_chunk`` e popado pelos metodos publicos
    (``cjsg``/``cjpg``) **antes** da validacao do schema, entao em runtime
    o mixin nao bloqueia nada — ele serve como **documentacao executavel**
    (cobertura via ``tests/schemas/test_cjsg_schemas.py::TestAutoChunkMixin``)
    e como rede de seguranca caso algum chamador interno bypassem o pop.
    """

    auto_chunk: bool = True


class CountOnlyMixin(BaseModel):
    """Flag opcional ``count_only`` para probe pre-scraping (issue #92).

    Default ``False``. Quando ``True``, o metodo publico (``cjsg``/``cjpg``):

    - Faz **uma unica** chamada de rede por janela (POST inicial + 1 GET no
      caso eSAJ; 1 GET no caso CJPG).
    - Extrai ``n_results`` do HTML via ``cjsg_n_results``/``cjpg_n_results``.
    - Retorna ``int`` em vez de ``pd.DataFrame``.
    - **Nao** salva HTML em disco, **nao** parseia conteudo.

    Multi-janela: se ``auto_chunk=True`` e o intervalo ``data_julgamento_*``
    excede o teto do tribunal (eSAJ: 366 dias), o metodo itera as janelas
    disjuntas (:func:`juscraper.utils.params.iter_date_windows`) e **soma
    as contagens**. Soma bruta — sem dedup por ``cd_acordao``/``id_processo``.
    Util para estimativa de wall-clock; pode divergir de ``len(cjsg(...))``
    no caminho normal quando ha documentos republicados (mesma chave em
    janelas distintas).

    **Fail-fast no auto-chunk** (divergencia deliberada do caminho normal):
    o caminho normal (:func:`juscraper.courts._esaj.base.run_auto_chunk`)
    tolera falha por janela como :class:`UserWarning` e devolve parcial
    deduplicado. ``count_only`` usa ``sum()`` — qualquer ``ValueError`` em
    uma janela aborta toda a iteracao e propaga limpo. Estimativa parcial
    silenciosa seria mais perigosa que erro explicito.

    Tribunais que ainda nao implementam ``count_only`` **nao devem herdar**
    deste mixin — ``extra='forbid'`` da classe concreta rejeita o flag com
    :class:`TypeError`, sinalizando ao usuario que o endpoint nao expoe a
    feature ainda. Hoje (refs #92): familia eSAJ cjsg (TJAC/TJAL/TJAM/TJCE/
    TJMS/TJSP) + TJSP cjpg.

    Nota: como :class:`AutoChunkMixin`, o flag ``count_only`` e consumido
    no metodo publico **antes** da validacao completa do schema — o caminho
    count_only chama o probe diretamente e nao passa por ``cjsg_download``/
    ``cjpg_download``. O mixin documenta a API publica e da rede de seguranca
    via paridade de assinatura/docstring.
    """

    count_only: bool = False


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
