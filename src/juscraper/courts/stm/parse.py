"""Parsers das páginas de resultados das buscas de jurisprudência e de processos do STM."""
from __future__ import annotations

import re
from typing import Any

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


# Aba de processos: a capa de cada feito, com as partes e os representantes.
COLUNAS_PROCESSOS = [
    "processo",
    "classe",
    "orgao",
    "conselho",
    "relator",
    "revisor",
    "juiz",
    "data_autuacao",
    "situacao",
    "assunto",
    "partes",
    "representantes",
    "url_processo",
]
# Campos da capa, reconhecidos pelo rótulo do ``<dt>`` (sem os dois-pontos): rótulo -> coluna.
_COLUNA_DO_ROTULO = {
    "Número do Feito": "processo",
    "Classe": "classe",
    "Orgão": "orgao",
    "Conselho": "conselho",
    "Relator(a)": "relator",
    "Revisor(a)": "revisor",
    "Juiz(a)": "juiz",
    "Data de Autuação": "data_autuacao",
    "Situação": "situacao",
}
_FORMATO_DA_AUTUACAO = "%d/%m/%Y %H:%M:%S"


def _texto_corrido(tag: Tag) -> str | None:
    """Texto da tag com os espaços e as quebras de linha reduzidos a um espaço."""
    return " ".join(tag.get_text().split()) or None


def _parse_parte(tipo: str | None, dd: Tag) -> dict[str, str | None]:
    """Parte do processo; ``qualificacao`` é o posto e a força que o portal mostra no ícone."""
    icone = dd.find("img", class_="icone-forca")
    return {"tipo": tipo, "nome": _texto_corrido(dd), "qualificacao": str(icone.get("title")) if icone else None}


def _parse_representante(tipo: str | None, dd: Tag) -> dict[str, Any]:
    """Representante e as partes que ele representa."""
    nome = dd.find("summary")
    return {
        "tipo": tipo,
        "nome": _texto_corrido(nome) if nome else None,
        "partes": [_texto_corrido(parte) for parte in dd.select("div.parte")],
    }


def _parse_processo(painel: Tag) -> dict[str, Any]:
    """Lê um painel de processo: a capa e as seções "Assuntos", "Partes" e "Representantes".

    O painel é uma lista só (``<dl>``), com as seções separadas por
    ``div.row-title``; nas duas últimas, um ``<dt>`` com o tipo vale para os
    ``<dd>`` que vêm até o próximo. Seção que não é uma dessas quatro
    ("Feitos Relacionados", nos processos em papel) fica de fora.
    """
    linha: dict[str, Any] = dict.fromkeys(COLUNAS_PROCESSOS)
    linha |= {"partes": [], "representantes": []}
    assuntos: list[str | None] = []
    link = painel.select_one(".label-processo a[href]")
    linha["url_processo"] = str(link["href"]) if link else None
    secao, rotulo = "Capa do Processo", ""
    for tag in painel.select("div.row-title, dt, dd"):
        if tag.name == "div":
            secao, rotulo = tag.get_text().strip(), ""
        elif tag.name == "dt":
            rotulo = tag.get_text().strip().rstrip(":")
        elif secao == "Assuntos":
            assuntos.append(_texto_corrido(tag))
        elif secao == "Partes":
            linha["partes"].append(_parse_parte(rotulo or None, tag))
        elif secao == "Representantes":
            linha["representantes"].append(_parse_representante(rotulo or None, tag))
        elif secao == "Capa do Processo" and rotulo in _COLUNA_DO_ROTULO:
            linha[_COLUNA_DO_ROTULO[rotulo]] = _texto_corrido(tag)
    # Um texto só, como no ``assunto`` do cjsg; o portal numera os assuntos ("1) ... 2) ...").
    linha["assunto"] = " ".join(filter(None, assuntos)) or None
    return linha


def processos_parse_manager(paginas: list[str]) -> pd.DataFrame:
    """Extrai os processos das páginas baixadas por ``listar_processos_download``.

    Cada processo é um ``div.panel`` com a capa numa lista
    (``dl.dl-horizontal``); os demais painéis da página não têm essa lista.
    ``data_autuacao`` vira ``datetime``; o restante sai como o portal publica.
    """
    linhas: list[dict[str, Any]] = []
    for html in paginas:
        soup = BeautifulSoup(html, "html.parser")
        linhas.extend(_parse_processo(painel) for painel in soup.select("div.panel:has(dl.dl-horizontal)"))
    df = pd.DataFrame(linhas, columns=COLUNAS_PROCESSOS)
    # Como nas datas do cjsg, o valor fora do formato vira ``NaT`` em vez de derrubar a coleta.
    df["data_autuacao"] = pd.to_datetime(df["data_autuacao"], format=_FORMATO_DA_AUTUACAO, errors="coerce")
    return df
