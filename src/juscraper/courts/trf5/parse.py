"""HTML parser for TRF5 PJe ``ConsultaPublica`` detail pages.

PJe renders the detail page as XHTML with stable ID suffixes
(``processoEvento``, ``processoPartesPoloAtivoResumidoList``, etc.) and
labeled ``<div class="propertyView">`` panels. This parser walks the
labels by visible text and the tables by ID suffix, so deployment-specific
``j_idNNN`` prefixes don't matter.
"""
from __future__ import annotations

import re
import warnings
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# The detail HTML is XHTML with an ``<?xml?>`` prolog; BS4's HTML parser
# handles it but emits a noisy warning every parse. Filter once at import.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


_PROCESS_LABELS = {
    # Visible label -> output key. Labels carry HTML entities in raw bytes
    # (``N&uacute;mero``); BS4 decodes them when ``get_text`` runs.
    "Número Processo": "processo",
    "Data da Distribuição": "data_distribuicao",
    "Classe Judicial": "classe",
    "Assunto": "assunto",
    "Jurisdição": "jurisdicao",
    "Órgão Julgador": "orgao_julgador",
    "Endereço": "endereco_orgao",
}


def _norm_ws(text: str | None) -> str | None:
    if text is None:
        return None
    s = re.sub(r"\s+", " ", text).strip()
    return s or None


def _parse_property_views(soup: BeautifulSoup) -> dict[str, str | None]:
    """Pull ``label -> value`` pairs out of the top ``propertyView`` panels."""
    out: dict[str, str | None] = {key: None for key in _PROCESS_LABELS.values()}
    for div in soup.select("div.propertyView"):
        label_el = div.find(class_="name")
        value_el = div.find(class_="value")
        if not label_el or not value_el:
            continue
        label = _norm_ws(label_el.get_text())
        if not label:
            continue
        for visible, key in _PROCESS_LABELS.items():
            if label.startswith(visible):
                out[key] = _norm_ws(value_el.get_text(separator=" "))
                break
    return out


def _parse_polo(soup: BeautifulSoup, suffix: str) -> list[dict[str, str | None]]:
    """Parse a polo (ativo/passivo) participants table into a list of dicts.

    TRF5 renders 2 ``<td>`` cells per row (participant text, then status).
    Reading the *last two* non-empty cells is forward-compatible if a leading
    cell is later added (TRF3 already renders 3 cells with an empty leader).
    """
    table = soup.find(
        "table", id=lambda i: bool(i and i.endswith(f":{suffix}"))
    )
    if not table:
        return []
    out: list[dict[str, str | None]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < 2:
            continue
        participante = _norm_ws(cells[-2].get_text(separator=" "))
        situacao = _norm_ws(cells[-1].get_text(separator=" "))
        if participante:
            out.append({"participante": participante, "situacao": situacao})
    return out


_MOV_RE = re.compile(
    r"^\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})\s*-\s*(.+?)\s*$",
    flags=re.DOTALL,
)


def _parse_movimentacoes(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    """Parse the movimentações table into ``[{data, descricao, documento}, ...]``.

    Each row's first cell carries the timestamped movement; the second carries
    a related document descriptor when there is one (most rows leave it empty).
    """
    table = soup.find("table", id=lambda i: bool(i and i.endswith(":processoEvento")))
    if not table:
        return []
    out: list[dict[str, str | None]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        mov_text = _norm_ws(cells[0].get_text(separator=" "))
        if not mov_text:
            continue
        m = _MOV_RE.match(mov_text)
        if m:
            data, descricao = m.group(1), _norm_ws(m.group(2))
        else:
            data, descricao = None, mov_text
        documento = (
            _norm_ws(cells[1].get_text(separator=" ")) if len(cells) > 1 else None
        )
        out.append({"data": data, "descricao": descricao, "documento": documento})
    return out


_DOC_RE = re.compile(
    r"ID:\s*(\d+)\s*-\s*([\d\-:.\s]+?)\s*-\s*(.+?)$",
    flags=re.DOTALL,
)


def _parse_documentos(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    """Parse the documentos table into ``[{id, data, descricao}, ...]``.

    PJe formats each row as ``ID: <id> - <yyyy-MM-dd HH:MM:SS.fff> - <descricao>``.
    Rows that don't match keep their full text in ``descricao`` so we don't
    drop data when the format drifts.
    """
    table = soup.find(
        "table", id=lambda i: bool(i and i.endswith(":processoDocumentoGridTab"))
    )
    if not table:
        return []
    out: list[dict[str, str | None]] = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        text = _norm_ws(cells[0].get_text(separator=" ")) or ""
        # Strip the "Visualizar documentos" link prefix when present.
        text = re.sub(r"^Visualizar documentos\s*", "", text, flags=re.IGNORECASE)
        text = text.strip(" |")
        if not text:
            continue
        m = _DOC_RE.search(text)
        if m:
            out.append(
                {
                    "id": m.group(1),
                    "data": _norm_ws(m.group(2)),
                    "descricao": _norm_ws(m.group(3)),
                }
            )
        else:
            out.append({"id": None, "data": None, "descricao": text})
    return out


def parse_detail(html: str) -> dict[str, Any]:
    """Parse a TRF5 PJe detail page into a flat record.

    Returns a dict with the canonical scalar columns
    (``processo``, ``data_distribuicao``, ``classe``, ``assunto``,
    ``jurisdicao``, ``orgao_julgador``, ``endereco_orgao``) plus four
    list-typed columns (``polo_ativo``, ``polo_passivo``, ``movimentacoes``,
    ``documentos``). Missing sections come back as empty lists / ``None``
    rather than raising — sigilo or partially-rendered pages still yield
    a row.
    """
    soup = BeautifulSoup(html, "lxml")
    record: dict[str, Any] = _parse_property_views(soup)
    record["polo_ativo"] = _parse_polo(soup, "processoPartesPoloAtivoResumidoList")
    record["polo_passivo"] = _parse_polo(soup, "processoPartesPoloPassivoResumidoList")
    record["movimentacoes"] = _parse_movimentacoes(soup)
    record["documentos"] = _parse_documentos(soup)
    return record
