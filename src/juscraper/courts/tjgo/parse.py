"""Parsing helpers for the TJGO jurisprudence search."""
from __future__ import annotations

import html as html_mod
import re
from datetime import datetime
from typing import Any

import pandas as pd

_RESULT_RE = re.compile(
    r'<div class="search-result">(.*?)</div>\s*<div class="search-result-',
    re.DOTALL,
)
_RESULT_FALLBACK_RE = re.compile(
    r'<div class="search-result">(.*?)(?=<div class="search-result">)',
    re.DOTALL,
)
_PROC_RE = re.compile(r"(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})")
_ID_ARQUIVO_RE = re.compile(
    r"abrirArquivo\('ConsultaJurisprudencia',\s*'(\d+)'\)"
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_PUBL_RE = re.compile(
    r"Publicado em\s*(\d{2}/\d{2}/\d{4}(?:\s*\d{2}:\d{2}:\d{2})?)"
)


def _clean(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = html_mod.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _parse_date(raw: Any):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _split_blocks(html: str) -> list:
    # Split HTML into result blocks. Each result is a <div class="search-result">
    # followed by paragraphs; blocks end when the next search-result or the
    # pagination footer starts.
    marker = '<div class="search-result">'
    parts = html.split(marker)
    if len(parts) <= 1:
        return []
    blocks = []
    for chunk in parts[1:]:
        end = chunk.find('<div class="search-result-pagination')
        if end == -1:
            end = len(chunk)
        blocks.append(chunk[:end])
    return blocks


def _parse_block(block: str) -> dict:
    proc_match = _PROC_RE.search(block)
    processo = proc_match.group(1) if proc_match else None

    id_arquivo_match = _ID_ARQUIVO_RE.search(block)
    id_arquivo = id_arquivo_match.group(1) if id_arquivo_match else None

    # The block has a predictable sequence of <p> blocks:
    # <p><b>serventia</b></p>
    # <p><b><i>relator</i></b></p>
    # <p><b>tipo</b></p>
    # <p><b><i>Publicado em ...</i></b></p>
    # <p class="conteudoTexto">texto</p>
    paragraphs = re.findall(r"<p([^>]*)>(.*?)</p>", block, re.DOTALL)
    serventia: str | None = None
    relator: str | None = None
    tipo: str | None = None
    publicacao_raw: str | None = None
    texto: str | None = None
    for attrs, content in paragraphs:
        cleaned = _clean(content)
        if "conteudoTexto" in attrs:
            texto = cleaned
            continue
        if not cleaned:
            continue
        if cleaned.startswith("Publicado em"):
            publ_match = _PUBL_RE.search(cleaned)
            publicacao_raw = publ_match.group(1) if publ_match else None
            continue
        if serventia is None:
            serventia = cleaned
        elif relator is None:
            relator = cleaned
        elif tipo is None:
            tipo = cleaned

    return {
        "processo": processo,
        "id_arquivo": id_arquivo,
        "serventia": serventia,
        "relator": relator,
        "tipo_ato": tipo,
        "data_publicacao": _parse_date(publicacao_raw),
        "texto": texto,
    }


def cjsg_parse(raw_pages: list) -> pd.DataFrame:
    """Transform raw HTML pages into a tidy DataFrame."""
    rows: list = []
    for html in raw_pages:
        if not html:
            continue
        for block in _split_blocks(html):
            rows.append(_parse_block(block))
    return pd.DataFrame(rows)
