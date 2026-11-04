"""Helpers compartilhados pelos testes do juscraper.

Janela de referência
--------------------
Os testes release usam a mesma janela fixa em todos os tribunais: julgamento
de 10/03/2025 a 13/03/2025 (segunda a quinta, sem feriado, fora do recesso de
dezembro, janeiro e julho) e publicação de 10/03/2025 a 29/04/2025 (terça),
porque a publicação costuma vir dias ou semanas depois do julgamento.

Quatro dias bastam para trazer resultado mesmo em tribunal que publica pouco,
e a janela é estreita o bastante para que um filtro quebrado apareça: qualquer
data fora dela quer dizer que o backend ignorou o filtro.

O fim de cada janela precisa cair num dia seguido de dia útil com publicação.
O erro de limite mais comum em raspador é incluir o dia seguinte ao fim: somar
um dia à data final quando a API já inclui a meia-noite do dia informado, ou
converter o fim do dia de Brasília para UTC. As linhas que vazam assim têm a
data do dia seguinte, e o teste só as vê se esse dia tiver julgamento ou
publicação. Um fim na sexta deixa o vazamento cair no sábado, e um fim na
véspera de feriado deixa cair no feriado; nos dois casos o dia seguinte vem
vazio, o resultado parece correto e o teste passa com o raspador quebrado. A
janela antiga terminava numa sexta (14/03) e numa véspera de feriado (30/04,
antes do 1º de maio), e por isso o teste não pegava esse erro em nenhum
tribunal.

O fim certo é condição necessária, não suficiente. A asserção olha só a
primeira página, e as linhas vazadas só chegam a ela quando o backend ordena
por data decrescente ou quando o dia vazado pesa na janela. Na de julgamento,
de quatro dias, o dia seguinte vira cerca de um quinto dos resultados. Na de
publicação, de sete semanas, vira cerca de um trigésimo; num backend que
ordena por relevância, a primeira página pode vir sem nenhuma linha vazada e o
teste passa com o raspador quebrado.

``DATA_ALVO_BR`` abre as duas janelas; ``DATA_ALVO_FIM_BR`` fecha a de
julgamento e ``DATA_PUB_FIM_BR`` fecha a de publicação.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

DATA_ALVO_BR = "10/03/2025"
DATA_ALVO_FIM_BR = "13/03/2025"
DATA_ALVO_ISO = "2025-03-10"
DATA_ALVO_FIM_ISO = "2025-03-13"

_ALVO_START = date(2025, 3, 10)
_ALVO_END = date(2025, 3, 13)

# Publicação usually trails julgamento. When a scraper filters on publicação
# instead of (or in addition to) julgamento, allow a wider publicação window
# so that rows judged in the target week have time to be published.
DATA_PUB_FIM_BR = "29/04/2025"
DATA_PUB_FIM_ISO = "2025-04-29"
_PUB_END = date(2025, 4, 29)


def _find_date_column(df: pd.DataFrame) -> str | None:
    """Return the first column that looks like a judgment or publication date.

    Tribunals disagree on column naming; scan by substring to stay robust.
    Priority: judgment date > publication date > generic "data".
    """
    needles = (
        "data_julgamento",
        "dt_julgamento",
        "julgamento",
        "data_publicacao",
        "dt_publicacao",
        "publicacao",
        "data",
    )
    for needle in needles:
        for col in df.columns:
            if needle in col.lower():
                return str(col)
    return None


def _parse_row_date(raw: str) -> date | None:
    """Parse a row's date cell into a ``date``. Tolerant of BR, ISO, and ISO+time."""
    raw = raw.strip()
    if not raw or raw.lower() in {"nan", "nat", "none"}:
        return None
    # ISO first (YYYY-MM-DD, possibly with time)
    if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            pass
    # Brazilian DD/MM/YYYY
    if len(raw) >= 10 and raw[2] == "/" and raw[5] == "/":
        try:
            d, m, y = raw[:10].split("/")
            return date(int(y), int(m), int(d))
        except ValueError:
            pass
    return None


def assert_date_matches(df: pd.DataFrame) -> str | None:
    """Check that every row falls inside the reference window.

    Julgamento columns are validated against the narrow window
    (``DATA_ALVO_BR`` to ``DATA_ALVO_FIM_BR``). Publicação columns are
    validated against a widened window (``DATA_ALVO_BR`` to
    ``DATA_PUB_FIM_BR``) because publicação typically trails julgamento
    by days or weeks.

    Returns the date column name used for validation, or ``None`` if the
    scraper does not expose one (caller accepts count-only validation).
    """
    col = _find_date_column(df)
    if col is None:
        return None
    is_pub = "publicacao" in col.lower() or "public" in col.lower()
    end = _PUB_END if is_pub else _ALVO_END
    fim_br = DATA_PUB_FIM_BR if is_pub else DATA_ALVO_FIM_BR
    raw = df[col].astype(str).str.strip()
    parsed = [_parse_row_date(r) for r in raw]
    bad = [
        (r, p) for r, p in zip(raw, parsed, strict=False)
        if p is None or not (_ALVO_START <= p <= end)
    ]
    assert not bad, (
        f"Coluna {col!r} possui datas fora do intervalo "
        f"{DATA_ALVO_BR}–{fim_br}: "
        f"{[b[0] for b in bad[:5]]}"
    )
    return col


# Date-filter kwarg sets, tried in order. After the #84 refactor each
# tribunal's InputCJSG uses ``extra="forbid"``, so a tribunal that filters only
# by julgamento (TJSP, TJES, ...) raises ``TypeError`` when handed
# ``data_publicacao_*`` — and a publicação-only tribunal (TJBA, TJGO) does the
# reverse. The helpers below try each set and skip the ones the schema rejects;
# the first accepted, non-empty result wins. ``_BOTH_DATES`` comes first so an
# eSAJ-style tribunal that ANDs both (e.g. TJAM) still matches (publicação
# trails julgamento). Tribunals that reject *every* set — no date filter at all
# (TJAP) or annual-only granularity (TJRJ) — re-raise the ``TypeError`` and are
# marked xfail in the release suite.
_BOTH_DATES = {
    "data_julgamento_inicio": DATA_ALVO_BR,
    "data_julgamento_fim": DATA_ALVO_FIM_BR,
    "data_publicacao_inicio": DATA_ALVO_BR,
    "data_publicacao_fim": DATA_PUB_FIM_BR,
}
_JULGAMENTO_DATES = {
    "data_julgamento_inicio": DATA_ALVO_BR,
    "data_julgamento_fim": DATA_ALVO_FIM_BR,
}
_PUBLICACAO_DATES = {
    "data_publicacao_inicio": DATA_ALVO_BR,
    "data_publicacao_fim": DATA_PUB_FIM_BR,
}
_DATE_FILTER_SETS = (_BOTH_DATES, _JULGAMENTO_DATES, _PUBLICACAO_DATES)


def run_filtro_data_unica(scraper, **extra_kwargs) -> pd.DataFrame:
    """Execute the standard date-filter release test for a scraper.

    Tries each set in ``_DATE_FILTER_SETS`` order, skipping the ones the
    scraper's schema rejects (``extra="forbid"`` → ``TypeError``), and uses the
    first accepted set that returns rows. If every set is rejected the tribunal
    has no usable date filter and the ``TypeError`` is re-raised (the release
    suite xfails those tribunais).

    1. Try ``pesquisa=''``; if the scraper rejects it, fall back to ``'direito'``.
    2. Assert at least one result was returned.
    3. If the output has a date column, assert every row falls inside the
       reference window (see :func:`assert_date_matches`).
    """
    df = None
    accepted = False
    last_type_error: TypeError | None = None
    for date_filters in _DATE_FILTER_SETS:
        kwargs = {**date_filters, **extra_kwargs, "paginas": 1}
        try:
            df = _call_cjsg_with_fallback(scraper, kwargs)
        except TypeError as exc:  # schema rejects this date-filter set
            last_type_error = exc
            continue
        accepted = True
        if df is not None and len(df) > 0:
            break

    if not accepted and last_type_error is not None:
        raise last_type_error

    assert isinstance(df, pd.DataFrame), "cjsg deve retornar DataFrame"
    assert len(df) > 0, (
        f"Nenhum resultado retornado para a janela "
        f"{DATA_ALVO_BR}–{DATA_ALVO_FIM_BR}. O filtro de data pode estar "
        "sendo ignorado ou a semana escolhida pode estar fora do intervalo "
        "disponível."
    )
    assert_date_matches(df)
    return df


def _call_cjsg_with_fallback(scraper, kwargs: dict) -> pd.DataFrame:
    """Call ``scraper.cjsg`` first with empty pesquisa, then 'direito'.

    Some tribunals reject empty pesquisa with a ``ValueError``; others silently
    return an empty DataFrame. In both cases we fall back to the generic term
    'direito' so the caller can still exercise the date filter. A ``TypeError``
    (an unsupported date kwarg under ``extra="forbid"``) is *not* swallowed: it
    propagates so the caller can try the next date-filter set.
    """
    try:
        df = scraper.cjsg("", **kwargs)
    except ValueError:
        df = None
    if df is None or len(df) == 0:
        df = scraper.cjsg("direito", **kwargs)
    return df


def run_paginacao_data_unica(scraper, **extra_kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download ``paginas=1`` and ``paginas=range(1,3)`` with the date fixed.

    Uses the same date-filter resolution as :func:`run_filtro_data_unica`: tries
    each set in ``_DATE_FILTER_SETS`` order, skips the ones the schema rejects
    (``extra="forbid"`` → ``TypeError``), and uses the first accepted set that
    returns rows — so a julgamento-only tribunal (TJSP) and a publicação-only one
    (TJBA) each get the filter their backend understands, and an accepted-but-empty
    set (e.g. a tribunal whose publicação index is empty for the target week)
    falls through to the next set instead of returning empty. Tribunals that
    reject every set re-raise the ``TypeError`` (xfailed in the release suite).

    Returns both DataFrames so the caller can decide whether to assert
    ``len(df2) >= len(df1)`` (only makes sense when the tribunal actually
    has more than one page of results for the target week).
    """
    result: tuple[pd.DataFrame, pd.DataFrame] | None = None
    last_type_error: TypeError | None = None
    for date_filters in _DATE_FILTER_SETS:
        base = {**date_filters, **extra_kwargs}
        try:
            df1 = _call_cjsg_with_fallback(scraper, {**base, "paginas": 1})
            df2 = _call_cjsg_with_fallback(scraper, {**base, "paginas": range(1, 3)})
        except TypeError as exc:  # schema rejects this date-filter set
            last_type_error = exc
            continue
        result = (df1, df2)
        if df1 is not None and len(df1) > 0:
            break

    if result is None and last_type_error is not None:
        raise last_type_error

    assert result is not None
    return result
