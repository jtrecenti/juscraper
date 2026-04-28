"""
Parse raw HTML results from the TJTO jurisprudence search.
"""
import re

import pandas as pd
from bs4 import BeautifulSoup


def _extract_uuid(container) -> str:
    """Extract the document UUID from a result container."""
    btn = container.select_one("[data-id]")
    return str(btn["data-id"]) if btn else ""


def _extract_processo(container) -> str:
    """Extract the formatted process number."""
    btn = container.select_one(".label-processo")
    if btn:
        text: str = btn.get_text(strip=True)
        match = re.search(r"[\d.-]+", text)
        return str(match.group(0)) if match else text
    return ""


def _extract_processo_link(container) -> str:
    """Extract the link to the process page."""
    link = container.select_one('a[href*="eproc"]')
    return str(link["href"]) if link else ""


def _extract_table_fields(container) -> dict:
    """Extract key-value pairs from the result table."""
    fields: dict = {}
    table = container.select_one("table")
    if not table:
        return fields
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) >= 2:
            key = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            fields[key] = value
    return fields


def _parse_single_page(html: str) -> list[dict]:
    """Parse a single page of TJTO results into a list of dicts."""
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(".panel-document")
    if not panel:
        return []

    containers = panel.select(".container.align-self-center")
    results = []
    for container in containers:
        fields = _extract_table_fields(container)
        processo = _extract_processo(container)
        uuid = _extract_uuid(container)

        resultado = {
            "processo": processo,
            "uuid": uuid,
            "classe": fields.get("Classe", ""),
            "tipo_julgamento": fields.get("Tipo Julgamento", ""),
            "assunto": fields.get("Assunto(s)", ""),
            "competencia": fields.get("Competência", ""),
            "relator": fields.get("Relator", "").strip(),
            "data_autuacao": fields.get("Data Autuação", ""),
            "data_julgamento": fields.get("Data Julgamento", ""),
            "processo_link": _extract_processo_link(container),
        }
        results.append(resultado)
    return results


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Parse raw HTML pages into a DataFrame.

    Args:
        resultados_brutos: List of raw HTML strings from cjsg_download_manager.

    Returns:
        DataFrame with the parsed results.
    """
    all_results = []
    for html in resultados_brutos:
        all_results.extend(_parse_single_page(html))

    df = pd.DataFrame(all_results)
    if df.empty:
        return df

    for col in ("data_julgamento", "data_autuacao"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    return df
