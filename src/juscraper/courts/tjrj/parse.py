"""Parsing helpers for the TJRJ jurisprudence search."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from juscraper.core.parse_utils import html_para_texto

_DATE_RE = re.compile(r"/Date\((-?\d+)\)/")


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
        rows.extend(
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
                # O texto vem com um parágrafo por linha (``\n``), sem ``<br>``.
                "ementa": html_para_texto(
                    doc.get("TextoSemFormat") or doc.get("Texto"), preservar_quebras=True
                )
                or "",
            }
            for doc in page.get("DocumentosConsulta", []) or []
        )
    return pd.DataFrame(rows)
