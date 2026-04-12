"""Parsing helpers for the TJRJ jurisprudence search."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")


def _strip_html(text: Any) -> str:
    if text is None:
        return ""
    return _TAG_RE.sub("", str(text)).strip()


def _parse_aspnet_date(raw: Any):
    if not isinstance(raw, str):
        return None
    match = _DATE_RE.search(raw)
    if not match:
        return None
    try:
        millis = int(match.group(1))
    except ValueError:
        return None
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).date()


def cjsg_parse(raw_pages: list) -> pd.DataFrame:
    """Transform raw JSON pages into a tidy DataFrame."""
    rows: list = []
    for page in raw_pages:
        if not page:
            continue
        for doc in page.get("DocumentosConsulta", []) or []:
            rows.append(
                {
                    "cod_documento": doc.get("CodDoc"),
                    "processo": doc.get("NumProcCnj") or doc.get("Processo"),
                    "numero_antigo": doc.get("NumAntigo"),
                    "classe": doc.get("Classe") or doc.get("DescrRecurso"),
                    "tipo_documento": doc.get("DescrTipDoc"),
                    "orgao_julgador": doc.get("NomeOrgJulg"),
                    "relator": doc.get("NomeMagRel"),
                    "data_julgamento": _parse_aspnet_date(doc.get("DtHrMov")),
                    "data_publicacao": _parse_aspnet_date(doc.get("DtHrPubl")),
                    "ementa": _strip_html(
                        doc.get("TextoSemFormat") or doc.get("Texto")
                    ),
                }
            )
    return pd.DataFrame(rows)
