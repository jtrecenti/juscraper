"""Parser da lista resumida da busca de jurisprudência do TRF3.

Cada documento é um ``li.acordao-retorno`` com quatro blocos:

* ``div.processo``: número do processo e botões com links;
* ``div.informacoes-basicas``: ``span.info`` em ordem fixa, que o portal não
  rotula (ver :func:`_informacoes_basicas`);
* ``div.ementa``: a ementa, ou o texto da decisão nas monocráticas;
* ``div.acordao`` (oculto): o inteiro teor.
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup, Tag

from ...core.parse_utils import coerce_date_columns
from ...utils.cnj import format_cnj

_PUBLICACAO_RE = re.compile(r"^(?P<meio>.*?)\s*DATA:\s*(?P<data>\d{2}/\d{2}/\d{4})", re.IGNORECASE)
_DECISAO_RE = re.compile(r"^(?:Julgamento|Decis[ãa]o)\s*:\s*(?P<data>\d{2}/\d{2}/\d{4})", re.IGNORECASE)

# Título da página de resultados -> base. As monocráticas do TRF3 e das Turmas
# Recursais têm o mesmo título; separa-as o critério "Base: Recursais".
_TITULO_BASE = {
    "base trf3": "acordaos",
    "base recursais": "turmas_recursais",
    "base monocráticas": "monocraticas",
}

COLUNAS_PRINCIPAIS = [
    "processo", "classe", "orgao_julgador", "relator", "relator_acordao",
    "data_julgamento", "data_publicacao", "meio_publicacao", "ementa",
    "base", "url_inteiro_teor", "inteiro_teor",
]


def _texto(tag: Tag | None, sep: str = " ") -> str | None:
    if tag is None:
        return None
    texto = tag.get_text(sep, strip=True)
    return texto or None


def _texto_com_quebras(tag: Tag | None) -> str | None:
    """Texto do bloco com uma quebra de linha por ``<br>``.

    As quebras do código-fonte HTML não contam: só ``<br>`` separa linhas.
    Também não se usa separador em ``get_text``, porque o portal marca o termo
    pesquisado com ``<em>`` no meio da frase e o separador partiria a frase
    ali. Sequências de ``<br>`` viram no máximo uma linha em branco.
    """
    if tag is None:
        return None
    for br in tag.find_all("br"):
        br.replace_with("\x00")
    linhas = [" ".join(parte.split()) for parte in tag.get_text().split("\x00")]
    texto = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    return texto or None


def _base_da_pagina(soup: BeautifulSoup) -> str | None:
    """Identifica a base pelo título e pelo critério que o portal ecoa."""
    titulo = (_texto(soup.select_one(".texto-titulo")) or "").lower()
    base = next((valor for chave, valor in _TITULO_BASE.items() if chave in titulo), None)
    if base == "monocraticas":
        criterio = (_texto(soup.select_one(".texto-subtitulo")) or "").lower()
        if re.search(r"base:\s*recursais", criterio):
            base = "monocraticas_turmas_recursais"
    return base


def _informacoes_basicas(item: Tag) -> dict[str, str | None]:
    """Lê os ``span.info`` de ``div.informacoes-basicas``.

    A ordem observada é classe, órgão julgador, relator, relator para o
    acórdão (só quando existe), publicação (``<meio> DATA: dd/mm/aaaa``) e
    data de julgamento (``Julgamento:`` ou, nas monocráticas, ``Decisão:``).
    Os três primeiros vêm sempre, mesmo vazios; por isso são lidos pela
    posição. Publicação e julgamento são reconhecidos pelo rótulo, e o que
    sobra entre o relator e eles é o relator para o acórdão, conforme o
    rótulo "Relator(a) para acórdão" da página do documento.
    """
    spans = [s.get_text(" ", strip=True) for s in item.select("div.informacoes-basicas > span.info")]
    info: dict[str, str | None] = {
        "classe": spans[0] if len(spans) > 0 else None,
        "orgao_julgador": spans[1] if len(spans) > 1 else None,
        "relator": spans[2] if len(spans) > 2 else None,
        "relator_acordao": None,
        "data_publicacao": None,
        "meio_publicacao": None,
        "data_julgamento": None,
    }
    extras: list[str] = []
    for span in spans[3:]:
        if decisao := _DECISAO_RE.match(span):
            info["data_julgamento"] = decisao.group("data")
        elif publicacao := _PUBLICACAO_RE.match(span):
            info["data_publicacao"] = publicacao.group("data")
            info["meio_publicacao"] = publicacao.group("meio").strip() or None
        elif span:
            extras.append(span)
    if extras:
        info["relator_acordao"] = "; ".join(extras)
    return {chave: (valor or None) for chave, valor in info.items()}


def _parse_item(item: Tag, base: str | None) -> dict:
    processo = _texto(item.select_one("div.processo > span.info"))
    integra = item.select_one("button.btn-integra-acordao[data-link]")
    return {
        "processo": processo,
        **_informacoes_basicas(item),
        "ementa": _texto_com_quebras(item.select_one("div.ementa")),
        "inteiro_teor": _texto_com_quebras(item.select_one("div.acordao")),
        "url_inteiro_teor": integra["data-link"] if integra else None,
        "base": base,
    }


def cjsg_parse_manager(resultados_brutos: list[str]) -> pd.DataFrame:
    """Converte as páginas da lista resumida em um DataFrame, uma linha por documento.

    Args:
        resultados_brutos: HTML de cada página, como devolvido por
            ``cjsg_download_manager``.

    Returns:
        DataFrame com as colunas de :data:`COLUNAS_PRINCIPAIS` primeiro.
        ``data_julgamento`` e ``data_publicacao`` saem como ``datetime.date``;
        ``processo`` sai no formato CNJ quando tem 20 dígitos.
    """
    registros: list[dict] = []
    for html in resultados_brutos:
        soup = BeautifulSoup(html, "html.parser")
        base = _base_da_pagina(soup)
        registros.extend(_parse_item(item, base) for item in soup.select("li.acordao-retorno"))

    df = pd.DataFrame(registros)
    if df.empty:
        return df

    coerce_date_columns(df, ["data_julgamento", "data_publicacao"], date_format="%d/%m/%Y")
    df["processo"] = df["processo"].apply(lambda v: format_cnj(v, strict=False))
    principais = [c for c in COLUNAS_PRINCIPAIS if c in df.columns]
    return df[principais + [c for c in df.columns if c not in principais]]
