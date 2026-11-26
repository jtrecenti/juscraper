"""
Parse raw HTML results from the TJPE jurisprudence search.
"""

import re
import warnings

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from juscraper.core.parse_utils import coerce_date_columns

FIELD_MAP = {
    "Processo": "processo",
    "Classe CNJ": "classe",
    "Assunto CNJ": "assunto",
    "Relator(a)": "relator",
    "Órgão Julgador": "orgao_julgador",
    "Data de Julgamento": "data_julgamento",
    "Data da Publicação/Fonte": "data_publicacao",
    "Data da Publicação": "data_publicacao",
    "Ementa": "ementa",
    "Acórdão": "acordao",
    "Decisão": "decisao",
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


def _valor_da_linha(row) -> str:
    """Texto da célula de valor, com os espaços colapsados (``""`` sem célula)."""
    value_td = row.find("td")
    if not value_td:
        return ""
    return " ".join(value_td.get_text(separator=" ", strip=True).split())


def _parse_result_table(table) -> dict:
    """Parse a single result table with alternating label/value rows.

    Célula vazia conta como rótulo ausente: o campo fica de fora e sai ``None``.
    """
    result = {}
    rows = table.find_all("tr")
    i = 0
    while i < len(rows):
        label_el = rows[i].find("label")
        field_name = FIELD_MAP.get(label_el.get_text(strip=True)) if label_el else None
        if field_name and i + 1 < len(rows):
            value = _valor_da_linha(rows[i + 1])
            if value:
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

    As decisões monocráticas não têm o rótulo ``Ementa`` no bloco: saem com
    ``ementa`` ausente (``None``), e a coluna existe mesmo quando nenhuma
    linha da busca tem ementa. O texto delas (rótulo ``Decisão``) sai em
    ``decisao``, que só existe quando alguma linha é monocrática e fica
    ausente nos acórdãos; o rótulo ``Data da Publicação`` (sem "/Fonte") sai
    em ``data_publicacao``. Célula vazia conta como rótulo ausente.
    """
    all_results = []

    for html in raw_pages:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html, "html.parser")

        inteiro_teor_urls = _extract_inteiro_teor_urls(soup)
        tables = _find_result_tables(soup)

        for idx, table in enumerate(tables):
            result = _parse_result_table(table)
            if result:
                if idx in inteiro_teor_urls:
                    result["url_inteiro_teor"] = inteiro_teor_urls[idx]
                all_results.append(result)

    df = pd.DataFrame(all_results)
    # O texto ausente vira ``None`` no embrulho dos métodos públicos
    # (``core.base``); aqui basta a coluna ``ementa`` existir sempre.
    if not df.empty and "ementa" not in df.columns:
        df["ementa"] = None

    coerce_date_columns(df, ["data_julgamento", "data_publicacao"], date_format="%d/%m/%Y")

    # Order columns
    preferred = [
        "processo", "classe", "assunto", "relator",
        "orgao_julgador", "data_julgamento", "data_publicacao",
        "ementa", "acordao", "decisao", "meio_tramitacao", "url_inteiro_teor",
    ]
    cols = [c for c in preferred if c in df.columns]
    cols += [c for c in df.columns if c not in preferred]
    df = df[cols]

    return df
