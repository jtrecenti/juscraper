"""Helpers compartilhados de parsing — limpeza HTML e normalização de datas.

Consolidam lógica duplicada hoje em vários ``courts/<xx>/parse.py``:

* ``clean_html`` substitui ``_clean_html`` privado de TJAP/TJRN/TJRO. A versão
  default (``decode_entities=True``) decodifica todas as entidades HTML5 via
  ``html.unescape`` (cobre nomeadas — ``&Aacute;``, ``&copy;``, ``&hellip;`` —
  e numéricas — ``&#193;``, ``&#xC1;``). ``decode_entities=False`` cobre o caso
  minimalista (só strip de tags e whitespace) usado por TJRN/TJRO.
* ``coerce_date_columns`` extrai o loop ``pd.to_datetime(..., errors="coerce").dt.date``
  repetido em ~13 tribunais.

Uso (a partir das Fases 1-4 do refactor #194)::

    from juscraper.core.parse_utils import clean_html, coerce_date_columns

A migração dos tribunais para esses helpers acontece nas issues #202–#205.
"""
from __future__ import annotations

import html
import re

import pandas as pd

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_html(text: str | None, decode_entities: bool = True) -> str | None:
    """Remove tags HTML e (opcionalmente) decodifica entidades.

    Args:
        text: Conteúdo bruto. ``None``/string vazia são retornados sem alteração.
        decode_entities: Se ``True`` (default), decodifica todas as entidades
            HTML5 via ``html.unescape`` — nomeadas (``&Aacute;``, ``&amp;``,
            ``&copy;``, ``&hellip;``, ...) e numéricas (``&#193;``, ``&#xC1;``).
            Se ``False``, só remove tags e colapsa whitespace.

    Returns:
        Texto limpo, ou o input sem alteração quando vazio/``None``.
    """
    if not text:
        return text

    text = _TAG_RE.sub(" ", text)

    if decode_entities:
        text = html.unescape(text)

    return _WHITESPACE_RE.sub(" ", text).strip()


def coerce_date_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Coage colunas para ``date`` via ``pd.to_datetime(..., errors="coerce").dt.date``.

    Mutação **in-place** + retorno (padrão pandas para encadeamento). Colunas
    ausentes em ``df`` são ignoradas silenciosamente. ``df`` vazio retorna direto.

    Args:
        df: DataFrame alvo.
        cols: Nomes de coluna candidatas a normalizar.

    Returns:
        O próprio ``df``.
    """
    if df.empty:
        return df
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date
    return df
