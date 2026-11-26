"""Helpers compartilhados de parsing — limpeza HTML e normalização de datas.

Consolidam lógica duplicada hoje em vários ``courts/<xx>/parse.py``:

* ``clean_html`` substitui ``_clean_html`` privado de TJAP/TJRN/TJRO. A versão
  default (``decode_entities=True``) decodifica todas as entidades HTML5 via
  ``html.unescape`` (cobre nomeadas — ``&Aacute;``, ``&copy;``, ``&hellip;`` —
  e numéricas — ``&#193;``, ``&#xC1;``). ``decode_entities=False`` cobre o caso
  minimalista (só strip de tags e whitespace) usado por TJRN/TJRO.
* ``coerce_date_columns`` extrai o loop ``pd.to_datetime(..., errors="coerce").dt.date``
  repetido em ~13 tribunais.
* ``clean_document_text`` limpa o texto bruto de documento dos agregadores
  JusBR e PDPJ, que servem a mesma API da PDPJ-CNJ.
* ``normalizar_texto`` e ``normalizar_colunas_texto`` tiram do texto corrido
  (ementa, decisão, inteiro teor) os caracteres que atrapalham a busca, sem
  mexer em quebras de linha nem em espaços.

Uso (a partir das Fases 1-4 do refactor #194)::

    from juscraper.core.parse_utils import clean_html, coerce_date_columns

A migração dos tribunais para esses helpers acontece nas issues #202–#205.
"""
from __future__ import annotations

import html
import re
from collections.abc import Iterable
from typing import overload

import pandas as pd

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

# Caracteres invisíveis que separam letras de uma mesma palavra: ``"MANDADO\u200c
# \u200cDE"`` no TJES, ``"§\xad 3º"`` no TJPI. Hífen discricionário e os de
# largura zero (espaço, não-agregador e agregador).
_INVISIVEIS = dict.fromkeys(map(ord, "\xad\u200b\u200c\u200d"))


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


def coerce_date_columns(
    df: pd.DataFrame,
    cols: list[str],
    *,
    date_format: str | None = None,
) -> pd.DataFrame:
    """Coage colunas para ``date`` via ``pd.to_datetime(..., errors="coerce").dt.date``.

    Mutação **in-place** + retorno (padrão pandas para encadeamento). Colunas
    ausentes em ``df`` são ignoradas silenciosamente. ``df`` vazio retorna direto.

    Args:
        df: DataFrame alvo.
        cols: Nomes de coluna candidatas a normalizar.
        date_format: Formato strptime explícito repassado a ``pd.to_datetime``
            (keyword-only). Use para tribunais que serializam datas em formato
            ambíguo como ``DD/MM/AAAA`` — sem isso, o pandas pode interpretar o
            valor no formato americano. Default ``None`` preserva o
            comportamento de inferência do pandas (ISO e similares).

    Returns:
        O próprio ``df``.

    Examples: Exemplo
        >>> # Default: inferência do pandas (ISO e similares).
        >>> coerce_date_columns(df, ["data_julgamento"])
        >>> # Formato ambíguo DD/MM/AAAA — usar ``date_format`` explícito.
        >>> coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
    """
    if df.empty:
        return df
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format=date_format, errors="coerce").dt.date
    return df


@overload
def normalizar_texto(texto: str) -> str: ...


@overload
def normalizar_texto(texto: object) -> object: ...


def normalizar_texto(texto: object) -> object:
    r"""Normaliza fins de linha, espaço não separável e caracteres invisíveis.

    Troca ``\r\n`` e ``\r`` por ``\n`` e ``\xa0`` por espaço comum, e remove
    o hífen discricionário (``\xad``) e os caracteres de largura zero
    (``\u200b``, ``\u200c`` e ``\u200d``). Uma busca por ``"art. 14"`` passa a
    achar o texto que o tribunal escreveu ``"art.\xa014"``.

    Não colapsa espaços, não remove tabulações e preserva as quebras de
    linha, que separam os parágrafos. Serve a texto corrido; HTML e RTF
    brutos devem ficar como vieram.

    Args:
        texto: Valor da coluna. O que não for ``str`` (``None``, ``NaN``,
            números) volta sem alteração.

    Returns:
        O texto normalizado, ou o próprio valor quando não é ``str``.
    """
    if not isinstance(texto, str):
        return texto
    return texto.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").translate(_INVISIVEIS)


def normalizar_colunas_texto(df: pd.DataFrame, colunas: Iterable[str]) -> pd.DataFrame:
    """Aplica :func:`normalizar_texto` às colunas de texto corrido de ``df``.

    Mutação **in-place** + retorno, como :func:`coerce_date_columns`. Colunas
    ausentes em ``df`` são ignoradas; valores que não são ``str`` ficam como
    estão.

    Args:
        df: DataFrame alvo.
        colunas: Nomes das colunas de texto corrido.

    Returns:
        O próprio ``df``.
    """
    for coluna in colunas:
        if coluna in df.columns:
            df[coluna] = df[coluna].map(normalizar_texto)
    return df


def clean_document_text(text: str | None) -> str | None:
    """Remove caracteres de controle e normaliza quebras de linha e espaços do texto bruto.

    Args:
        text: Texto como a API devolveu.

    Returns:
        O texto limpo, ou ``None`` quando a entrada é ``None``, vazia ou só tem
            espaço: documento sem texto aproveitável sai igual nos dois agregadores.
    """
    if not text:
        return None
    cleaned = normalizar_texto(text.replace("\x00", "").replace("\x1a", ""))
    cleaned = cleaned.replace("\u2028", "\n").replace("\u2029", "\n")
    return cleaned.strip() or None
