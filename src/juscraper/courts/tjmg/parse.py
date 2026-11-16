"""Parsing helpers for the TJMG jurisprudence search."""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlsplit

import pandas as pd

from juscraper.core.exceptions import HTTPSemanticError
from juscraper.core.parse_utils import clean_html, coerce_date_columns
from juscraper.utils.cnj import CNJ_FORMATADO_RE

_INTERNAL_RE = re.compile(r"(\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3})")
_TIPO_RE = re.compile(r"\d+\s*-\s*Processo:\s*([^<\n]+?)(?:<br|</)", re.IGNORECASE)
_RELATOR_RE = re.compile(
    r"<strong>\s*Relator\(a\):\s*</strong>\s*([^<\n]+)", re.IGNORECASE
)
_DJULG_RE = re.compile(
    r"<strong>\s*Data de Julgamento:\s*</strong>\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_DPUBL_RE = re.compile(
    r"Data da publica[^<]*?</strong>\s*(\d{2}/\d{2}/\d{4})",
    re.IGNORECASE,
)
_EMENTA_RE = re.compile(
    r"<strong>\s*Ementa:\s*</strong>(.*?)</div>", re.DOTALL | re.IGNORECASE
)
# Erro do banco do portal, mostrado no aviso da página no lugar dos resultados,
# como em "Ocorreu um erro na busca por Palavras - ORA-20000: Oracle Text error:
# DRG-10599: a coluna não está indexada".
_ERRO_DE_BUSCA_RE = re.compile(
    r'<p class="aviso">\s*(Ocorreu um erro na busca[^<]*)', re.IGNORECASE
)
# Com acórdãos de repetitivos entre os resultados, o portal mostra só a contagem
# por categoria, com um link para cada lista, e nenhum resultado.
_CATEGORIZADA_RE = re.compile(r"<h1>\s*Resultado da busca \(Categorizada\)", re.IGNORECASE)
_CATEGORIA_RE = re.compile(
    r"<td>([^<]+?):</td>\s*<td><a ([^>]*)>(\d+) documento\(s\) encontrado\(s\)</a>",
    re.IGNORECASE,
)
_HREF_RE = re.compile(r"""href=["']([^"']*)["']""", re.IGNORECASE)
_PROC_ID_RE = re.compile(
    r"procAno=(\d+)&procCodigo=(\d+)&procCodigoOrigem=(\d+)"
    r"&procNumero=(\d+)&procSequencial=(\d+)&procSeqAcordao=(\d+)"
)


class TJMGBuscaSemListaError(HTTPSemanticError):
    """O portal respondeu à busca sem a lista de resultados.

    Duas páginas observadas ao vivo viravam um DataFrame vazio, como se não
    houvesse resultados: o erro ``ORA-20000 ... DRG-10599: a coluna não está
    indexada``, nas buscas sem filtro de data e em algumas faixas longas, e a
    busca categorizada, quando há acórdãos de repetitivos no resultado.

    O ``cjsg_download`` levanta o erro do banco logo depois da página 1 e
    segue as listas da busca categorizada; o parse levanta os dois, para as
    páginas baixadas antes disso.
    """


def listas_da_busca_categorizada(html: str) -> list[tuple[str, dict[str, str]]]:
    """``(categoria, parâmetros do link)`` de cada lista da busca categorizada.

    Vazia quando ``html`` não é a busca categorizada. Os parâmetros são os da
    query do link, como ``{"excluirRepetitivos": "true", ...}`` para os
    acórdãos e ``{"listaClasse": "600", ...}`` para os de repetitivos.
    """
    if not _CATEGORIZADA_RE.search(html):
        return []
    listas = []
    for nome, atributos, _ in _CATEGORIA_RE.findall(html):
        href = _HREF_RE.search(atributos)
        link = href.group(1) if href else ""
        listas.append((clean_html(nome) or nome, dict(parse_qsl(urlsplit(unescape(link)).query))))
    return listas


def _busca_sem_lista(html: str) -> str | None:
    """Explica por que a página não traz a lista de resultados, ou ``None`` se traz."""
    erro = _ERRO_DE_BUSCA_RE.search(html)
    if erro:
        return (
            f"TJMG devolveu um erro de busca: {clean_html(erro.group(1))!r}. "
            "O portal falha assim sem filtro de data e em algumas faixas longas; "
            "informe um filtro de data com uma faixa menor."
        )
    if _CATEGORIZADA_RE.search(html):
        categorias = "; ".join(
            f"{clean_html(nome)}: {n}" for nome, _, n in _CATEGORIA_RE.findall(html)
        )
        return (
            f"TJMG devolveu a busca categorizada ({categorias}), que separa os "
            "acórdãos de repetitivos e não lista resultados. O formato dos links "
            "das categorias não foi reconhecido, ou a página foi baixada antes de "
            "o cjsg_download passar a seguir essas listas."
        )
    return None


def levantar_se_sem_lista(html: str) -> None:
    """Levanta :class:`TJMGBuscaSemListaError` se ``html`` não traz a lista de resultados."""
    motivo = _busca_sem_lista(html)
    if motivo:
        raise TJMGBuscaSemListaError(motivo)


def _split_blocks(html: str) -> list:
    parts = html.split('<div class="caixa_processo"')
    if len(parts) <= 1:
        return []
    # Each caixa_processo marks the start of a result. End at next caixa_processo.
    return list(parts[1:])


def _parse_block(block: str) -> dict:
    cnj_match = CNJ_FORMATADO_RE.search(block)
    internal_match = _INTERNAL_RE.search(block)
    tipo_match = _TIPO_RE.search(block)
    relator_match = _RELATOR_RE.search(block)
    djulg_match = _DJULG_RE.search(block)
    dpubl_match = _DPUBL_RE.search(block)
    ementa_match = _EMENTA_RE.search(block)
    proc_id_match = _PROC_ID_RE.search(block)

    ementa = clean_html(ementa_match.group(1)) if ementa_match else None
    if ementa:
        # Strip leading "EMENTA:" label that appears in the body text.
        ementa = re.sub(r"^EMENTA:\s*", "", ementa, flags=re.IGNORECASE)

    return {
        "processo": cnj_match.group(0) if cnj_match else None,
        "processo_interno": internal_match.group(1) if internal_match else None,
        "tipo_ato": clean_html(tipo_match.group(1)) if tipo_match else None,
        "relator": clean_html(relator_match.group(1)) if relator_match else None,
        "data_julgamento": djulg_match.group(1) if djulg_match else None,
        "data_publicacao": dpubl_match.group(1) if dpubl_match else None,
        "ementa": ementa,
        "proc_ano": proc_id_match.group(1) if proc_id_match else None,
        "proc_numero": proc_id_match.group(4) if proc_id_match else None,
    }


def cjsg_parse(raw_pages: list) -> pd.DataFrame:
    """Transform raw TJMG HTML pages into a tidy DataFrame."""
    rows: list = []
    for html in raw_pages:
        if not html:
            continue
        levantar_se_sem_lista(html)
        rows.extend(_parse_block(block) for block in _split_blocks(html))
    df = pd.DataFrame(rows)
    coerce_date_columns(df, ["data_julgamento", "data_publicacao"], date_format="%d/%m/%Y")
    return df
