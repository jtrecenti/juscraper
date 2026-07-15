"""Parse raw HTML results from the TJSC jurisprudence search (eproc)."""
import re

import pandas as pd
from bs4 import BeautifulSoup

_FIELD_MAP = {
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

_LABEL_REPLACEMENTS = str.maketrans({
    "Ã": "A",
    "Õ": "O",
    "Ç": "C",
    "É": "E",
    "Á": "A",
})


def _normalize_label(label: str) -> str:
    """Normalize only the accented characters historically accepted by TJSC."""
    return label.translate(_LABEL_REPLACEMENTS)


def _resolve_field(label: str) -> str | None:
    """Resolve exact, normalized, and partial labels in their original order."""
    normalized_label = _normalize_label(label)
    direct_match = _FIELD_MAP.get(label) or _FIELD_MAP.get(normalized_label)
    if direct_match:
        return direct_match

    for field_label, field_key in _FIELD_MAP.items():
        if field_label in label or field_label in normalized_label:
            return field_key
    return None


def _extract_class(value) -> str | None:
    """Extract the class description from the process field when present."""
    class_text = str(value.get_text(separator="\n", strip=True))
    lines = (line.strip() for line in class_text.split("\n") if line.strip())
    for line in lines:
        if not re.match(r"^[A-Z]{2,}", line) or "-" not in line:
            continue
        parts = line.split(" - ", 1)
        if len(parts) == 2:
            return parts[1].strip()
        break
    return None


def _extract_process_fields(value) -> dict[str, str]:
    """Extract the linked process number and the adjacent class description."""
    fields = {}
    link = value.find("a", class_="numero-processo")
    if link:
        fields["processo"] = link.get_text(strip=True).rstrip("/T")
    process_class = _extract_class(value)
    if process_class is not None:
        fields["classe"] = process_class
    return fields


def _store_text_field(result: dict, key: str, text: str) -> None:
    """Preserve the asymmetric precedence between DECISÃO and EMENTA."""
    if key == "ementa" or (key == "decisao" and "ementa" not in result):
        result["ementa"] = text
        return
    result[key] = text


def _parse_result_item(item) -> dict:
    """Parse a single resultadoItem div from the TJSC search page."""
    result = {}
    labels = item.find_all("div", class_="resLabel")
    values = item.find_all("div", class_="resValue")

    for label, value in zip(labels, values, strict=False):
        label_text = label.get_text(strip=True).upper()
        key = _resolve_field(label_text)
        if not key:
            continue

        if key == "processo":
            result.update(_extract_process_fields(value))
            continue
        _store_text_field(result, key, value.get_text(strip=True))

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
