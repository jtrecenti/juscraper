"""Parse raw HTML results from the TJRR jurisprudence search (JSF/PrimeFaces)."""
import re

import pandas as pd
from bs4 import BeautifulSoup


def _parse_result_div(div) -> dict:
    """Parse a single result div from the TJRR search page."""
    result = {}
    doc_fields = div.find_all("div", class_="docParagrafo")
    for field in doc_fields:
        title_div = field.find("div", class_="docTitulo")
        text_div = field.find("div", class_="docTexto")
        if not title_div or not text_div:
            continue
        title = title_div.get_text(strip=True).rstrip(":")
        text = text_div.get_text(strip=True)

        if "PROCESSO" in title.upper():
            # Extract process number and class
            lines = text_div.get_text(separator="\n").strip().split("\n")
            for line in lines:
                line = line.strip()
                if re.match(r"^\d{20}$", line):
                    result["processo"] = _format_cnj(line)
                elif re.match(r"^[A-Z]", line) and "Segredo" not in line:
                    result["classe"] = line.strip()
        elif "RELATOR" in title.upper():
            result["relator"] = text
        elif "JULGADOR" in title.upper():
            result["orgao_julgador"] = text
        elif "JULGAMENTO" in title.upper():
            result["data_julgamento"] = text
        elif "PUBLICA" in title.upper():
            result["data_publicacao"] = text
        elif "EMENTA" in title.upper():
            result["ementa"] = text

    return result


def _format_cnj(numero: str | None) -> str | None:
    """Format a raw 20-digit number as CNJ pattern."""
    if not numero or not numero.isdigit() or len(numero) != 20:
        return numero
    return (
        f"{numero[:7]}-{numero[7:9]}.{numero[9:13]}."
        f"{numero[13]}.{numero[14:16]}.{numero[16:]}"
    )


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJRR HTML responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw HTML strings from the TJRR search.
    """
    registros = []
    for html in resultados_brutos:
        soup = BeautifulSoup(html, "html.parser")
        result_divs = soup.find_all("div", id=lambda x: x and x.startswith("resultados"))
        for div in result_divs:
            registro = _parse_result_div(div)
            if registro:
                registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    principais = [
        "processo", "classe", "relator", "orgao_julgador",
        "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
