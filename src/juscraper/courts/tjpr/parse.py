"""
Functions for parsing specific to TJPR
"""
import pandas as pd
import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from juscraper.core.exceptions import RetryExhaustedError
from juscraper.core.http import RequestFn
from juscraper.core.parse_utils import coerce_date_columns

from .download import get_ementa_completa


def _extract_processo(dados_td: Tag) -> str:
    processo_a = dados_td.find("a", class_="decisao negrito")
    if processo_a:
        return str(processo_a.get_text(strip=True))

    processo = ""
    for div in dados_td.find_all("div"):
        if "Processo:" not in div.get_text():
            continue
        processo_div = div.find_all("div")
        if processo_div:
            processo = str(processo_div[0].get_text(strip=True))
    return processo


def _extract_labeled_value(
    dados_td: Tag,
    label: str,
    *,
    use_text_sibling: bool = False,
) -> str:
    label_text = dados_td.find(string=lambda text: text and label in text)
    if not label_text:
        return ""

    value = str(label_text).split(label)[-1].strip()
    if value or not use_text_sibling or label_text.parent is None:
        return value

    sibling = label_text.parent.find_next_sibling(string=True)
    return str(sibling).strip() if sibling else ""


def _extract_document_id(dados_td: Tag) -> str:
    process_input = dados_td.find("input", {"name": "idsSelecionados"})
    if not process_input or "value" not in process_input.attrs:
        return ""
    return str(process_input["value"])


def _extract_ementa(
    dados_td: Tag,
    ementa_td: Tag,
    criterio: str | None,
    request_fn: RequestFn | None,
) -> str:
    ementa = str(ementa_td.get_text("\n", strip=True))
    if "leia mais" not in ementa.lower():
        return ementa

    id_processo = _extract_document_id(dados_td)
    if not id_processo or not criterio or request_fn is None:
        return ementa

    try:
        return get_ementa_completa(request_fn, id_processo, criterio)
    except (requests.RequestException, RetryExhaustedError, AttributeError) as error:
        # A falha de uma ementa completa não invalida os demais resultados da página.
        return f"{ementa}\n[Erro ao buscar ementa completa: {error}]"


def _parse_row(
    row: Tag,
    criterio: str | None,
    request_fn: RequestFn | None,
) -> dict[str, object] | None:
    cols = row.find_all("td")
    if len(cols) < 2:
        return None

    dados_td, ementa_td = cols[:2]
    return {
        "processo": _extract_processo(dados_td),
        "orgao_julgador": _extract_labeled_value(dados_td, "Órgão Julgador:"),
        "relator": _extract_labeled_value(dados_td, "Relator:", use_text_sibling=True),
        "data_julgamento": _extract_labeled_value(dados_td, "Data Julgamento:", use_text_sibling=True),
        "ementa": _extract_ementa(dados_td, ementa_td, criterio, request_fn),
    }


def cjsg_parse(
    htmls,
    criterio=None,
    *,
    request_fn: RequestFn | None = None,
):
    """
    Extracts relevant data from the HTMLs returned by TJPR.
    Returns a DataFrame with the decisions.

    ``request_fn`` is used to fetch the full minute when a row is truncated
    with "Leia mais...". Without it the ementa stays truncated — useful for
    offline parsing of pre-downloaded pages.
    """
    resultados = []
    for html in htmls:
        soup = BeautifulSoup(html, "html.parser")
        tabela = soup.select_one("table.resultTable.jurisprudencia")
        if not tabela:
            continue
        for row in tabela.find_all("tr")[1:]:  # pula o cabeçalho
            result = _parse_row(row, criterio, request_fn)
            if result is not None:
                resultados.append(result)
    df = pd.DataFrame(resultados)
    coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
    return df
