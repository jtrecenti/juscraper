"""Parse raw HTML results from the TJPI jurisprudence search."""
import re

import pandas as pd
from bs4 import BeautifulSoup


def _extract_field(text: str, field: str) -> str | None:
    """Extract a named field from the full-text decision block."""
    pattern = rf"{field}\s*[:\s]*\s*(.+?)(?=\n[A-Z\(\[]|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _parse_item(item_div) -> dict:
    """Parse a single result item from the TJPI search page."""
    result = {}

    # Get badge (type of decision)
    badge = item_div.find("span", class_=lambda c: c and "badge" in c)
    if badge:
        result["tipo"] = badge.get_text(strip=True)

    # Get publication date from h6
    h6 = item_div.find("h6")
    if h6:
        text = h6.get_text(strip=True)
        date_match = re.search(r"(\d{2}/\d{2}/\d{4})", text)
        if date_match:
            result["data_publicacao"] = date_match.group(1)

    # Get visible summary
    summary_div = item_div.find("div", class_="text-justify")
    if summary_div:
        # Get only the direct text, not hidden children
        visible_text = summary_div.find(string=True, recursive=False)
        if visible_text:
            result["resumo"] = visible_text.strip()

    # Get hidden full text (contains the complete decision)
    hidden_div = item_div.select_one("div.d-none")
    if hidden_div:
        full_text = hidden_div.get_text(strip=True)
        result["inteiro_teor"] = full_text

        # Extract structured fields from full text
        processo = re.search(r"PROCESSO\s*(?:N[oº°]?\s*:?\s*)?(\d[\d.-]+)", full_text, re.IGNORECASE)
        if processo:
            result["processo"] = processo.group(1).strip()

        classe = re.search(r"CLASSE:\s*(.+?)(?:\s*\(\d+\))", full_text, re.IGNORECASE)
        if classe:
            result["classe"] = classe.group(1).strip()

        assunto = re.search(r"ASSUNTO\(?S?\)?\s*:\s*\[(.+?)\]", full_text, re.IGNORECASE)
        if assunto:
            result["assunto"] = assunto.group(1).strip()

        # Extract ementa
        ementa_match = re.search(r"Ementa:\s*(.+?)(?:\.\s+[IVX]+\.\s|$)", full_text, re.IGNORECASE | re.DOTALL)
        if ementa_match:
            result["ementa"] = ementa_match.group(1).strip()
        else:
            # Fallback: use visible summary as ementa
            if summary_div:
                result["ementa"] = summary_div.get_text(strip=True)[:2000]

    return result


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJPI HTML responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw HTML strings from the TJPI search.
    """
    registros = []
    for html in resultados_brutos:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("div", attrs={"data-controller": "clipboard reveal"})
        for item in items:
            registro = _parse_item(item)
            if registro:
                registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    if "data_publicacao" in df.columns:
        df["data_publicacao"] = pd.to_datetime(
            df["data_publicacao"], format="%d/%m/%Y", errors="coerce"
        ).dt.date

    principais = [
        "processo", "tipo", "classe", "assunto",
        "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
