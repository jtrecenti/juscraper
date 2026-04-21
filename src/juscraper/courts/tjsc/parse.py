"""Parse raw HTML results from the TJSC jurisprudence search (eproc)."""
import re

import pandas as pd
from bs4 import BeautifulSoup


def _parse_result_item(item) -> dict:
    """Parse a single resultadoItem div from the TJSC search page."""
    result = {}
    labels = item.find_all("div", class_="resLabel")
    values = item.find_all("div", class_="resValue")

    field_map = {
        "PROCESSO": "processo",
        "UF": "uf",
        "ORGAO JULGADOR": "orgao_julgador",
        "ÓRGÃO JULGADOR": "orgao_julgador",
        "DATA DO JULGAMENTO": "data_julgamento",
        "DATA DA PUBLICAÇÃO": "data_publicacao",
        "DATA DA PUBLICACAO": "data_publicacao",
        "RELATOR": "relator",
        "RELATORA": "relator",
        "EMENTA": "ementa",
        "DECISÃO": "decisao",
        "DECISAO": "decisao",
    }

    for label, value in zip(labels, values):
        label_text = label.get_text(strip=True).upper()
        # Normalize accented chars for matching
        label_norm = (
            label_text.replace("Ã", "A").replace("Õ", "O")
            .replace("Ç", "C").replace("É", "E").replace("Á", "A")
        )

        key = field_map.get(label_text) or field_map.get(label_norm)
        if not key:
            # Try partial matching
            for field_label, field_key in field_map.items():
                if field_label in label_text or field_label in label_norm:
                    key = field_key
                    break
        if not key:
            continue

        text = value.get_text(strip=True)

        if key == "processo":
            # Extract process number from link
            link = value.find("a", class_="numero-processo")
            if link:
                result["processo"] = link.get_text(strip=True).rstrip("/T")
            # Extract class from remaining text
            classe_text = value.get_text(separator="\n", strip=True)
            lines = [ln.strip() for ln in classe_text.split("\n") if ln.strip()]
            for line in lines:
                if re.match(r"^[A-Z]{2,}", line) and "-" in line:
                    # e.g. "AI - Agravo de Instrumento"
                    parts = line.split(" - ", 1)
                    if len(parts) == 2:
                        result["classe"] = parts[1].strip()
                    break
        elif key == "ementa":
            result["ementa"] = text
        elif key == "decisao" and "ementa" not in result:
            result["ementa"] = text
        else:
            result[key] = text

    return result


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJSC HTML responses.

    Returns a DataFrame with the decisions.

    Args:
        resultados_brutos: List of raw HTML strings from the TJSC search.
    """
    registros = []
    for html in resultados_brutos:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.find_all("div", class_="resultadoItem")
        for item in items:
            registro = _parse_result_item(item)
            if registro and ("ementa" in registro or "processo" in registro):
                registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    principais = [
        "processo", "classe", "orgao_julgador", "relator",
        "data_julgamento", "data_publicacao", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
