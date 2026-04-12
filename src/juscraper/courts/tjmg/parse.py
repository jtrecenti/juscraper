"""Parsing helpers for the TJMG jurisprudence search."""
from __future__ import annotations

import html as html_mod
import re
from datetime import datetime
from typing import Any

import pandas as pd

_CNJ_RE = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
_INTERNAL_RE = re.compile(r"(\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3})")
_TIPO_RE = re.compile(r"\d+\s*-\s*Processo:\s*([^<\n]+?)(?:<br|</)", re.IGNORECASE)
_RELATOR_RE = re.compile(
    r"<strong>\s*Relator\(a\):\s*</strong>\s*([^<\n]+)", re.IGNORECASE
)
_DJULG_RE = re.compile(
    r"<strong>\s*Data de Julgamento:\s*</strong>\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_DPUBL_RE = re.compile(
    r"Data da publica[^<]*?</strong>\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_EMENTA_RE = re.compile(
    r"<strong>\s*Ementa:\s*</strong>(.*?)</div>", re.DOTALL | re.IGNORECASE
)
_PROC_ID_RE = re.compile(
    r"procAno=(\d+)&procCodigo=(\d+)&procCodigoOrigem=(\d+)"
    r"&procNumero=(\d+)&procSequencial=(\d+)&procSeqAcordao=(\d+)"
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = html_mod.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _parse_date(raw: Any):
    if not raw:
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _split_blocks(html: str) -> list:
    parts = html.split('<div class="caixa_processo"')
    if len(parts) <= 1:
        return []
    blocks = []
    # Each caixa_processo marks the start of a result. End at next caixa_processo.
    for chunk in parts[1:]:
        blocks.append(chunk)
    return blocks


def _parse_block(block: str) -> dict:
    cnj_match = _CNJ_RE.search(block)
    internal_match = _INTERNAL_RE.search(block)
    tipo_match = _TIPO_RE.search(block)
    relator_match = _RELATOR_RE.search(block)
    djulg_match = _DJULG_RE.search(block)
    dpubl_match = _DPUBL_RE.search(block)
    ementa_match = _EMENTA_RE.search(block)
    proc_id_match = _PROC_ID_RE.search(block)

    ementa = _clean(ementa_match.group(1)) if ementa_match else None
    if ementa:
        # Strip leading "EMENTA:" label that appears in the body text.
        ementa = re.sub(r"^EMENTA:\s*", "", ementa, flags=re.IGNORECASE)

    return {
        "processo": cnj_match.group(0) if cnj_match else None,
        "processo_interno": internal_match.group(1) if internal_match else None,
        "tipo_ato": _clean(tipo_match.group(1)) if tipo_match else None,
        "relator": _clean(relator_match.group(1)) if relator_match else None,
        "data_julgamento": _parse_date(djulg_match.group(1)) if djulg_match else None,
        "data_publicacao": _parse_date(dpubl_match.group(1)) if dpubl_match else None,
        "ementa": ementa,
        "proc_ano": proc_id_match.group(1) if proc_id_match else None,
        "proc_numero": proc_id_match.group(4) if proc_id_match else None,
    }


def cjsg_parse(raw_pages: list) -> pd.DataFrame:
    """Transform raw TJMG HTML pages into a tidy DataFrame."""
    rows: list = []
    for html in raw_pages:
        if not html:
            continue
        for block in _split_blocks(html):
            rows.append(_parse_block(block))
    return pd.DataFrame(rows)
