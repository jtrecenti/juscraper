"""HTML parser for TRF6 eproc ``Detalhes do Processo`` pages.

The detail page uses the SEI/Infra component framework: the cover panel is
a ``<fieldset>`` with ``<dt id="lblXXX">label</dt><dd id="txtXXX">value</dd>``
pairs, and the variable-length sections (assuntos, partes, eventos) are
``<table class="infraTable">``. Two of those tables share ``summary="Assuntos"``
because the eventos table inherits the same summary via copy/paste in the
source — they're disambiguated by the header row text.
"""
from __future__ import annotations

import re
import warnings
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# eproc serves XHTML with an ``<?xml?>`` prolog; BS4's HTML parser handles
# it but emits a warning every parse. Filter once at module load.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# ``<dd id="...">`` -> output key. We key off the ``dd`` ID rather than the
# label text so the parser is encoding-agnostic (labels carry latin-1 bytes).
_CAPA_FIELD_IDS = {
    "txtNumProcesso": "processo",
    "txtAutuacao": "data_autuacao",
    "txtSituacao": "situacao",
    "txtMagistrado": "magistrado",
    "txtClasse": "classe",
}

# ``orgaoJulgador`` doesn't have a stable ``txt*`` ID in this deployment;
# match the label text suffix instead.
_ORGAO_LABEL_PREFIX = "rg\xe3o Julgador"  # "Órgão Julgador" with ó as latin-1 byte


def _norm_ws(text: str | None) -> str | None:
    if text is None:
        return None
    s = re.sub(r"\s+", " ", text).strip()
    return s or None


def _parse_capa(soup: BeautifulSoup) -> dict[str, str | None]:
    """Pull dt/dd pairs from the ``Capa do Processo`` fieldset."""
    out: dict[str, str | None] = {key: None for key in _CAPA_FIELD_IDS.values()}
    out["orgao_julgador"] = None
    fieldset = None
    for fs in soup.find_all("fieldset"):
        leg = fs.find("legend")
        if leg and "Capa" in leg.get_text():
            fieldset = fs
            break
    if not fieldset:
        return out
    for dt in fieldset.find_all("dt"):
        dd = dt.find_next_sibling("dd")
        if not dd:
            continue
        dd_id = dd.get("id") or ""
        if dd_id in _CAPA_FIELD_IDS:
            out[_CAPA_FIELD_IDS[dd_id]] = _norm_ws(dd.get_text(separator=" "))
            continue
        # Fall back to label text for fields without stable IDs (e.g.
        # órgão julgador renders as ``<dd>`` with no id in some samples).
        label_text = dt.get_text(strip=True)
        if _ORGAO_LABEL_PREFIX in label_text or "Julgador" in label_text:
            out["orgao_julgador"] = _norm_ws(dd.get_text(separator=" "))
    return out


def _parse_assuntos(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    """Parse the assuntos table (``Código | Descrição | Principal``)."""
    for tbl in soup.find_all("table", summary="Assuntos"):
        rows = tbl.find_all("tr")
        if not rows:
            continue
        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        # The eventos table also has summary="Assuntos" (same source bug);
        # disambiguate by header content.
        if not (
            header_cells
            and "digo" in header_cells[0]
            and "Principal" in (header_cells[-1] if header_cells else "")
        ):
            continue
        out: list[dict[str, str | None]] = []
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 3:
                continue
            out.append(
                {
                    "codigo": _norm_ws(cells[0].get_text(separator=" ")),
                    "descricao": _norm_ws(cells[1].get_text(separator=" ")),
                    "principal": _norm_ws(cells[2].get_text(separator=" ")),
                }
            )
        return out
    return []


def _parse_partes(
    soup: BeautifulSoup,
) -> dict[str, list[dict[str, str | None]]]:
    """Parse the ``Partes e Representantes`` table.

    The table is laid out as alternating ``<tr><th>POLE</th>...</tr>``
    header rows and ``<tr><td>...</td>...</tr>`` data rows. Common poles
    encountered: ``AUTOR``, ``RÉU``, ``MPF``, ``PERITO``. The header row
    can carry one or two ``<th>`` (one when only one pole appears in that
    band; two when both are side by side).
    """
    poles: dict[str, list[dict[str, str | None]]] = {}
    tbl = soup.find("table", summary="Partes e Representantes")
    if not tbl:
        return poles
    rows = tbl.find_all("tr")
    current_keys: list[str] = []
    for tr in rows:
        ths = tr.find_all("th")
        tds = tr.find_all("td")
        if ths and not tds:
            current_keys = [_norm_ws(th.get_text(separator=" ")) or "" for th in ths]
            for key in current_keys:
                poles.setdefault(key, [])
            continue
        if tds and current_keys:
            for key, td in zip(current_keys, tds):
                text = _norm_ws(td.get_text(separator=" | "))
                if text:
                    poles.setdefault(key, []).append({"descricao": text})
    return poles


def _parse_eventos(soup: BeautifulSoup) -> list[dict[str, str | None]]:
    """Parse the eventos (movements) table.

    Header row: ``Evento | Data/Hora | Descrição | Usuário | Documentos``.
    Documents column carries either the placeholder
    ``"Evento não gerou documento(s)"`` or a list of document descriptors —
    we keep the raw text either way so the caller can post-process if
    needed.
    """
    for tbl in soup.find_all("table", summary="Assuntos"):
        rows = tbl.find_all("tr")
        if not rows:
            continue
        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not (header_cells and header_cells[0].startswith("Evento")):
            continue
        out: list[dict[str, str | None]] = []
        for tr in rows[1:]:
            cells = tr.find_all(["td", "th"])
            if len(cells) < 5:
                continue
            out.append(
                {
                    "evento": _norm_ws(cells[0].get_text(separator=" ")),
                    "data_hora": _norm_ws(cells[1].get_text(separator=" ")),
                    "descricao": _norm_ws(cells[2].get_text(separator=" ")),
                    "usuario": _norm_ws(cells[3].get_text(separator=" ")),
                    "documentos": _norm_ws(cells[4].get_text(separator=" ")),
                }
            )
        return out
    return []


def parse_detail(html: str) -> dict[str, Any]:
    """Parse a TRF6 detail page into a flat record.

    Keys: ``processo``, ``data_autuacao``, ``situacao``, ``magistrado``,
    ``classe``, ``orgao_julgador``, ``assuntos`` (list), ``polo_ativo``,
    ``polo_passivo``, ``mpf``, ``perito`` (each a list), ``movimentacoes``
    (list). Any pole the table doesn't have comes back as an empty list.
    """
    soup = BeautifulSoup(html, "lxml")
    record: dict[str, Any] = _parse_capa(soup)
    record["assuntos"] = _parse_assuntos(soup)
    poles = _parse_partes(soup)
    # Map TRF6's pole headers to canonical Portuguese keys used elsewhere
    # in juscraper. Keys not present default to empty lists rather than
    # omission so the DataFrame schema is stable.
    record["polo_ativo"] = poles.get("AUTOR", [])
    record["polo_passivo"] = poles.get("R\xc9U", []) or poles.get("RÉU", [])
    record["mpf"] = poles.get("MPF", [])
    record["perito"] = poles.get("PERITO", [])
    record["movimentacoes"] = _parse_eventos(soup)
    return record
