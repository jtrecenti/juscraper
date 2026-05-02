"""Helpers compartilhados de parsing — limpeza HTML e normalização de datas.

Consolidam lógica duplicada hoje em vários ``courts/<xx>/parse.py``:

* ``clean_html`` substitui ``_clean_html`` privado de TJAP/TJRN/TJRO. A versão
  default (``decode_entities=True``) é a do TJAP — completa, com tags + entidades
  nomeadas (``html.unescape``) + entidades numéricas (``&#NNN;``/``&#xHH;``).
  ``decode_entities=False`` cobre o caso minimalista (só strip de tags e
  whitespace) usado por TJRN/TJRO.
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
_NAMED_ENTITY_RE = re.compile(
    r"&([A-Za-z]+(?:acute|grave|circ|tilde|uml|cedil|ring|slash|lig));"
)
_NUMERIC_DEC_ENTITY_RE = re.compile(r"&#(\d+);")
_NUMERIC_HEX_ENTITY_RE = re.compile(r"&#x([0-9a-fA-F]+);")
_WHITESPACE_RE = re.compile(r"\s+")

_BASIC_ENTITIES: dict[str, str] = {
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
    "&nbsp;": " ",
}


def clean_html(text: str | None, decode_entities: bool = True) -> str | None:
    """Remove tags HTML e (opcionalmente) decodifica entidades.

    Args:
        text: Conteúdo bruto. ``None``/string vazia são retornados sem alteração.
        decode_entities: Se ``True`` (default), decodifica entidades nomeadas
            (``&Aacute;``, ``&amp;``, ...) e numéricas (``&#193;``, ``&#xC1;``).
            Se ``False``, só remove tags e colapsa whitespace.

    Returns:
        Texto limpo, ou o input sem alteração quando vazio/``None``.
    """
    if not text:
        return text

    text = _TAG_RE.sub(" ", text)

    if decode_entities:
        for raw, decoded in _BASIC_ENTITIES.items():
            text = text.replace(raw, decoded)
        text = _NAMED_ENTITY_RE.sub(lambda m: html.unescape(m.group(0)), text)
        text = _NUMERIC_DEC_ENTITY_RE.sub(lambda m: chr(int(m.group(1))), text)
        text = _NUMERIC_HEX_ENTITY_RE.sub(lambda m: chr(int(m.group(1), 16)), text)

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
