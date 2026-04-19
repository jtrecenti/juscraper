"""Shared helpers for juscraper tests.

Reference date strategy
-----------------------
Release tests use a single fixed work week across every tribunal:

    10/03/2025 – 14/03/2025 (Monday–Friday, no holidays, outside the judicial
    recess of December, January and July).

A week-long window (rather than a single day) is wide enough to produce at
least one result even in tribunais that publish sparsely, while still being
narrow enough that a broken date filter stands out: any date outside this
window means the backend ignored the filter entirely.

``DATA_ALVO_BR`` is the start of the window; ``DATA_ALVO_FIM_BR`` is the end.
Helpers accept both and the assertion checks that every row falls inside.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

DATA_ALVO_BR = "10/03/2025"
DATA_ALVO_FIM_BR = "14/03/2025"
DATA_ALVO_ISO = "2025-03-10"
DATA_ALVO_FIM_ISO = "2025-03-14"

_ALVO_START = date(2025, 3, 10)
_ALVO_END = date(2025, 3, 14)


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
                return col
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
    """Check that every row falls inside the reference work week.

    Returns the date column name used for validation, or ``None`` if the
    scraper does not expose one (caller accepts count-only validation).
    """
    col = _find_date_column(df)
    if col is None:
        return None
    raw = df[col].astype(str).str.strip()
    parsed = [_parse_row_date(r) for r in raw]
    bad = [
        (r, p) for r, p in zip(raw, parsed)
        if p is None or not (_ALVO_START <= p <= _ALVO_END)
    ]
    assert not bad, (
        f"Coluna {col!r} possui datas fora do intervalo "
        f"{DATA_ALVO_BR}–{DATA_ALVO_FIM_BR}: "
        f"{[b[0] for b in bad[:5]]}"
    )
    return col


def run_filtro_data_unica(scraper, **extra_kwargs) -> pd.DataFrame:
    """Execute the standard date-filter release test for a scraper.

    1. Try ``pesquisa=''``; if the scraper rejects it, fall back to ``'direito'``.
    2. Assert at least one result was returned.
    3. If the output has a date column, assert every row falls inside the
       reference window (10/03/2025 – 14/03/2025).
    """
    # Tribunais divergem na dimensão temporal suportada: alguns filtram por
    # data de julgamento, outros por data de publicação.  Passamos ambas para
    # cobrir os dois casos — o scraper usa a que implementa e ignora a outra.
    kwargs = {
        "data_julgamento_inicio": DATA_ALVO_BR,
        "data_julgamento_fim": DATA_ALVO_FIM_BR,
        "data_publicacao_inicio": DATA_ALVO_BR,
        "data_publicacao_fim": DATA_ALVO_FIM_BR,
        "paginas": 1,
    }
    kwargs.update(extra_kwargs)

    df = _call_cjsg_with_fallback(scraper, kwargs)

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

    Some tribunals reject empty pesquisa with an exception; others silently
    return an empty DataFrame.  In both cases we fall back to the generic
    term 'direito' so the caller can still exercise the date filter.
    """
    try:
        df = scraper.cjsg("", **kwargs)
    except (ValueError, TypeError):
        df = None
    if df is None or len(df) == 0:
        df = scraper.cjsg("direito", **kwargs)
    return df


def run_paginacao_data_unica(scraper, **extra_kwargs) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download ``paginas=1`` and ``paginas=range(1,3)`` with the date fixed.

    Returns both DataFrames so the caller can decide whether to assert
    ``len(df2) > len(df1)`` (only makes sense when the tribunal actually
    has more than one page of results for the target week).
    """
    base = {
        "data_julgamento_inicio": DATA_ALVO_BR,
        "data_julgamento_fim": DATA_ALVO_FIM_BR,
        "data_publicacao_inicio": DATA_ALVO_BR,
        "data_publicacao_fim": DATA_ALVO_FIM_BR,
    }
    base.update(extra_kwargs)

    df1 = _call_cjsg_with_fallback(scraper, {**base, "paginas": 1})
    df2 = _call_cjsg_with_fallback(scraper, {**base, "paginas": range(1, 3)})
    return df1, df2
