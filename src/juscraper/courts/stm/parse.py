"""Parser das páginas de resultados da busca de jurisprudência do STM."""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup, Tag

from juscraper.core.parse_utils import coerce_date_columns

COLUNAS = [
    "processo",
    "classe",
    "relator",
    "relator_acordao",
    "revisor",
    "assunto",
    "data_autuacao",
    "data_julgamento",
    "data_publicacao",
    "ementa",
    "url_inteiro_teor",
    "id_documento",
]
_COLUNAS_DE_DATA = ["data_autuacao", "data_julgamento", "data_publicacao"]

# Campos que o portal marca com ``data-id``: coluna -> valor do atributo.
_CAMPOS_DATA_ID = {
    "processo": "numero_processo",
    "classe": "classe",
    "relator": "ministro_relator",
    "relator_acordao": "ministro_relator_acordao",
    "data_autuacao": "data_autuacao",
    "data_julgamento": "data_julgamento",
    "data_publicacao": "data_publicacao",
    "ementa": "ementa",
    "id_documento": "id",
}
# Campos sem ``data-id``, reconhecidos pelo rótulo do ``<dt>``.
_CAMPOS_ROTULO = {"revisor": "Revisor(a):", "assunto": "Assuntos:"}
_URL_INTEIRO_TEOR = re.compile(r"openInteiroTeor\('([^']+)'\)")


def _texto(tag: Tag | None) -> str | None:
    return tag.get_text().strip() or None if tag else None


def _parse_documento(painel: Tag) -> dict[str, str | None]:
    linha = {coluna: _texto(painel.find(attrs={"data-id": data_id})) for coluna, data_id in _CAMPOS_DATA_ID.items()}
    for coluna, rotulo in _CAMPOS_ROTULO.items():
        dt = painel.find("dt", string=rotulo)
        linha[coluna] = _texto(dt.find_next_sibling("dd")) if dt else None
    url = _URL_INTEIRO_TEOR.search(" ".join(str(botao.get("onclick", "")) for botao in painel.find_all("button")))
    linha["url_inteiro_teor"] = url.group(1) if url else None
    return linha


def cjsg_parse_manager(paginas: list[str]) -> pd.DataFrame:
    """Extrai os documentos das páginas baixadas por ``cjsg_download``.

    Cada documento é um ``div.panel`` com o número do processo em
    ``data-id="numero_processo"``; os demais painéis da página (dicas, janela
    modal) não têm esse campo e ficam de fora. As datas viram ``date``; o
    restante sai como o portal publica.
    """
    linhas: list[dict[str, str | None]] = []
    for html in paginas:
        soup = BeautifulSoup(html, "html.parser")
        linhas.extend(
            _parse_documento(painel)
            for painel in soup.select("div.panel")
            if painel.find(attrs={"data-id": "numero_processo"})
        )
    df = pd.DataFrame(linhas, columns=COLUNAS)
    return coerce_date_columns(df, _COLUNAS_DE_DATA, date_format="%d/%m/%Y")
