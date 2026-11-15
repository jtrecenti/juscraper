"""Parsing helpers for the TJGO jurisprudence search."""
from __future__ import annotations

import html as html_mod
import re
from datetime import datetime
from typing import Any

import pandas as pd

# Abertura de cada resultado. No HTML atual do portal a div traz atributos
# (``data-realizador``, ``data-id-arquivo``) depois da classe; o literal
# ``<div class="search-result">`` deixava de casar e o cjsg voltava vazio.
# Os valores podem conter ``>`` (``data-classe-acao='... -> Recursos -> ...'``),
# entao a tag so termina fora das aspas.
_RESULT_OPEN_RE = re.compile(
    r'<div class="search-result"'
    r"""(?:\s+[\w-]+(?:=(?:"[^"]*"|'[^']*'|[^\s>]+))?)*\s*>"""
)
_PROC_RE = re.compile(r"(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})")
_ID_ARQUIVO_RE = re.compile(
    r"abrirArquivo\('ConsultaJurisprudencia',\s*'(\d+)'\)"
)
# Mantido local (em vez de core.parse_utils.clean_html) porque o backend do
# Projudi envolve trechos do texto em tags inline (<b>, <i>) e clean_html
# substitui tags por espaco, introduzindo espacos antes de pontuacao
# (<b>foo</b>, -> "foo ,"). Mesma decisao registrada em TJMT no batch 3.
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Paragrafo de data: "Publicado em ..." no formato antigo; no HTML atual
# (nov/2026) o mesmo campo vem rotulado "Julgado em ..." (nos samples antigos
# "Publicado em" coincide com o "julgado em" do texto de copia do bloco), e o
# paragrafo do tipo de ato deixou de existir.
_DATA_RE = re.compile(
    r"(?:Publicado|Julgado) em\s*(\d{2}/\d{2}/\d{4}(?:\s*\d{2}:\d{2}:\d{2})?)?"
)


def _clean(text: str) -> str:
    text = _TAG_RE.sub("", text)
    text = html_mod.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def _parse_date(raw: Any):
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def has_results(html: str) -> bool:
    """Indica se a pagina traz ao menos um bloco de resultado."""
    return _RESULT_OPEN_RE.search(html) is not None


def _split_blocks(html: str) -> list:
    # Split HTML into result blocks. Each result is a <div class="search-result">
    # followed by paragraphs; blocks end when the next search-result or the
    # pagination footer starts.
    parts = _RESULT_OPEN_RE.split(html)
    if len(parts) <= 1:
        return []
    blocks = []
    for chunk in parts[1:]:
        end = chunk.find('<div class="search-result-pagination')
        if end == -1:
            end = len(chunk)
        blocks.append(chunk[:end])
    return blocks


def _parse_block(block: str) -> dict:
    proc_match = _PROC_RE.search(block)
    processo = proc_match.group(1) if proc_match else None

    id_arquivo_match = _ID_ARQUIVO_RE.search(block)
    id_arquivo = id_arquivo_match.group(1) if id_arquivo_match else None

    # The block has a predictable sequence of <p> blocks:
    # <p><b>serventia</b></p>
    # <p><b><i>relator</i></b></p>
    # <p><b>tipo</b></p>
    # <p><b><i>Publicado em ...</i></b></p>
    # <p class="conteudoTexto">texto</p>
    # No HTML atual nao ha o <p> do tipo e a data vem como "Julgado em ...".
    # Depois do texto vem o bloco de trechos do INTEIRO TEOR, que nao entra:
    # sem o <p> do tipo, o primeiro desses paragrafos cairia em ``tipo_ato``.
    paragraphs = re.findall(r"<p([^>]*)>(.*?)</p>", block, re.DOTALL)
    serventia: str | None = None
    relator: str | None = None
    tipo: str | None = None
    data_raw: str | None = None
    texto: str | None = None
    for attrs, content in paragraphs:
        cleaned = _clean(content)
        if "conteudoTexto" in attrs:
            texto = cleaned
            break
        if not cleaned:
            continue
        data_match = _DATA_RE.match(cleaned)
        if data_match:
            data_raw = data_match.group(1)
            continue
        if serventia is None:
            serventia = cleaned
        elif relator is None:
            relator = cleaned
        elif tipo is None:
            tipo = cleaned

    return {
        "processo": processo,
        "id_arquivo": id_arquivo,
        "serventia": serventia,
        "relator": relator,
        "tipo_ato": tipo,
        "data_publicacao": _parse_date(data_raw),
        "texto": texto,
    }


def cjsg_parse(raw_pages: list) -> pd.DataFrame:
    """Transform raw HTML pages into a tidy DataFrame."""
    rows: list = []
    for html in raw_pages:
        if not html:
            continue
        rows.extend(_parse_block(block) for block in _split_blocks(html))
    return pd.DataFrame(rows)
