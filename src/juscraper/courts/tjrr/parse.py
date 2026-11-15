"""Parse raw HTML results from the TJRR jurisprudence search (JSF/PrimeFaces)."""
import re

import pandas as pd
from bs4 import BeautifulSoup

from juscraper.core.avisos import avisar
from juscraper.core.parse_utils import coerce_date_columns
from juscraper.utils.cnj import format_cnj

from .download import _ACORDAOS, _MONOCRATICAS

# A página de resultados tem duas tabelas: ``dataTablePesquisa`` (acórdãos) e
# ``dataTablePesquisa2`` (decisões monocráticas). Nas páginas 2+ o download
# junta só as linhas (``<tr>``) das duas, sem a tabela em volta; por isso a
# origem é lida da própria linha, no id dos botões dela
# (``formPesquisa:j_idtNNN:dataTablePesquisa2:10:j_idt222``), presentes em
# toda linha dos samples.
_TIPO_POR_TABELA = {_ACORDAOS: "acordao", _MONOCRATICAS: "monocratica"}
_TABELA_NO_ID_RE = re.compile(rf":({_MONOCRATICAS}|{_ACORDAOS}):")


def _tipo_decisao(div) -> str | None:
    """Diz se a linha veio da tabela de acórdãos ou da de monocráticas."""
    for tag in div.find_all(id=True):
        match = _TABELA_NO_ID_RE.search(tag["id"])
        if match:
            return _TIPO_POR_TABELA[match.group(1)]
    return None


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
                    result["processo"] = format_cnj(line, strict=False)
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


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """Extract relevant data from the raw TJRR HTML responses.

    Returns a DataFrame with the decisions. ``tipo_decisao`` diz a tabela de
    origem de cada linha: ``"acordao"`` ou ``"monocratica"``; ``None``, com
    ``UserWarning``, quando a linha não a indica.

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
                registro["tipo_decisao"] = _tipo_decisao(div)
                registros.append(registro)

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    sem_tipo = int(df["tipo_decisao"].isna().sum())
    if sem_tipo:
        avisar(
            f"TJRR: {sem_tipo} de {len(df)} linha(s) sem tipo_decisao: a linha não "
            "indica se veio da tabela de acórdãos ou da de decisões monocráticas."
        )

    coerce_date_columns(df, ["data_julgamento", "data_publicacao"], date_format="%d/%m/%Y")

    principais = [
        "processo", "classe", "relator", "orgao_julgador",
        "data_julgamento", "data_publicacao", "ementa", "tipo_decisao",
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_restantes = [c for c in df.columns if c not in principais]
    df = df[cols_principais + cols_restantes]
    return df
