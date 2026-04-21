"""
Parse raw HTML results from the TJPE jurisprudence search.
"""

import re
import warnings

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

FIELD_MAP = {
    "Processo": "processo",
    "Classe CNJ": "classe_cnj",
    "Assunto CNJ": "assunto_cnj",
    "Relator(a)": "relator",
    "Órgão Julgador": "orgao_julgador",
    "Data de Julgamento": "data_julgamento",
    "Data da Publicação/Fonte": "data_publicacao",
    "Ementa": "ementa",
    "Acórdão": "acordao",
    "Meio de Tramitação": "meio_tramitacao",
}


def _extract_inteiro_teor_urls(soup) -> dict[int, str]:
    """Extract 'Íntegra do Acórdão' URLs indexed by result position."""
    urls = {}
    base = "https://www.tjpe.jus.br"
    for i, link in enumerate(soup.find_all("a", href=re.compile(r"downloadInteiroTeor"))):
        href = link["href"]
        if href.startswith("/"):
            href = base + href
        urls[i] = href
    return urls


def _find_result_tables(soup) -> list:
    """Find all result data tables by locating 'Processo' labels."""
    tables = []
    for label in soup.find_all("label", string=lambda t: t and t.strip() == "Processo"):
        table = label.find_parent("table")
        if table and table not in tables:
            tables.append(table)
    return tables


def _parse_result_table(table) -> dict:
    """Parse a single result table with alternating label/value rows."""
    result = {}
    rows = table.find_all("tr")
    i = 0
    while i < len(rows):
        label_el = rows[i].find("label")
        if label_el:
            label_text = label_el.get_text(strip=True)
            field_name = FIELD_MAP.get(label_text)
            if field_name and i + 1 < len(rows):
                value_td = rows[i + 1].find("td")
                if value_td:
                    value = value_td.get_text(separator=" ", strip=True)
                    # Collapse multiple whitespace
                    value = " ".join(value.split())
                    result[field_name] = value
                i += 2
                continue
        i += 1
    return result


def cjsg_parse(raw_pages: list[str]) -> pd.DataFrame:
    """
    Parse a list of raw HTML pages from cjsg_download into a DataFrame.

    Each page contains up to 5 result blocks structured as label/value
    table rows.
    """
    all_results = []

    for html in raw_pages:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "lxml")

        inteiro_teor_urls = _extract_inteiro_teor_urls(soup)
        tables = _find_result_tables(soup)

        for idx, table in enumerate(tables):
            result = _parse_result_table(table)
            if result:
                if idx in inteiro_teor_urls:
                    result["url_inteiro_teor"] = inteiro_teor_urls[idx]
                all_results.append(result)

    df = pd.DataFrame(all_results)

    # Convert date columns
    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%d/%m/%Y", errors="coerce").dt.date

    # Order columns
    preferred = [
        "processo", "classe_cnj", "assunto_cnj", "relator",
        "orgao_julgador", "data_julgamento", "data_publicacao",
        "ementa", "acordao", "meio_tramitacao", "url_inteiro_teor",
    ]
    cols = [c for c in preferred if c in df.columns]
    cols += [c for c in df.columns if c not in preferred]
    df = df[cols]

    return df
