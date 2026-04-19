"""Parse raw results from the TJRS jurisprudence search.

The new WordPress endpoint returns a JSON envelope where ``data.html``
is pre-rendered HTML. Each result is a ``div.result-juris`` with the
fields laid out in two columns; dates live in ``.result-detail``.
"""
import re

import pandas as pd
from bs4 import BeautifulSoup


def _text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def _strip_label(text: str, label: str) -> str:
    """Strip a leading ``Label:`` and surrounding whitespace."""
    out = re.sub(rf"^\s*{re.escape(label)}\s*:?\s*", "", text, flags=re.IGNORECASE)
    return out.strip()


def _find_field(container, label: str) -> str:
    """Return the value after a ``<strong>Label:</strong>`` or ``<span>`` label."""
    for node in container.find_all(["strong", "span"]):
        if label.lower() in _text(node).lower():
            parent = node.parent
            raw = _text(parent)
            return _strip_label(raw, label)
    return ""


def _parse_result_block(block) -> dict:
    """Parse a single ``.result-juris`` block into a dict."""
    row = {}
    numero_a = block.select_one("a.a-results")
    row["processo"] = _text(numero_a) if numero_a else ""
    url = numero_a.get("href", "") if numero_a else ""
    row["url"] = url

    inteiro_teor = block.select_one(
        'a[href*="inteiro-teor"], a[href*="exibe-html-jurisprudencia"]'
    )
    row["url_inteiro_teor"] = inteiro_teor.get("href", "") if inteiro_teor else ""

    for label, col in [
        ("Tipo de processo", "tipo_processo"),
        ("Tribunal", "tribunal"),
        ("Classe CNJ", "classe_cnj"),
        ("Relator", "relator"),
        ("Órgão Julgador", "orgao_julgador"),
        ("Comarca de Origem", "comarca_origem"),
        ("Seção", "secao"),
        ("Assunto CNJ", "assunto_cnj"),
        ("Decisão", "decisao"),
    ]:
        row[col] = _find_field(block, label)

    for label, col in [
        ("Data de Julgamento", "data_julgamento"),
        ("Publicação", "data_publicacao"),
    ]:
        row[col] = _find_field(block, label)

    ementa_div = block.select_one(".ementa-result")
    if ementa_div:
        row["ementa"] = _strip_label(_text(ementa_div), "Ementa").replace(
            "Ver íntegra da ementa", ""
        ).strip("… .")

    return row


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant fields from the raw WordPress AJAX responses.

    Returns a DataFrame with one row per decision.
    """
    registros = []
    for payload in resultados_brutos:
        data = (payload or {}).get("data") or {}
        html = data.get("html") or ""
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        for block in soup.select("div.result-juris"):
            registros.append(_parse_result_block(block))

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    for col in ("data_julgamento", "data_publicacao"):
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col], format="%d/%m/%Y", errors="coerce"
            ).dt.date

    principais = [
        "processo", "relator", "orgao_julgador", "data_julgamento",
        "data_publicacao", "classe_cnj", "assunto_cnj", "tribunal",
        "tipo_processo", "comarca_origem", "secao", "decisao", "url",
        "url_inteiro_teor", "ementa",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    return df[cols_principais + cols_restantes]
