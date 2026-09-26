"""Parsing helpers for the TJMG second-degree case lookup (``cposg``).

Colunas produzidas por :func:`cposg_parse` (uma linha por recurso):
``id_cnj``, ``processo``, ``processo_interno``, ``segredo_justica``,
``situacao``, ``secretaria``, ``classe``, ``assunto``, ``orgao_julgador``,
``data_cadastramento``, ``data_distribuicao`` e ``partes``.

``partes`` e uma lista de dicts ``{"tipo", "nome", "baixa", "advogados"}``,
onde ``advogados`` e uma lista de ``{"oab", "nome"}``.
"""
from __future__ import annotations

import re

import pandas as pd
from bs4 import BeautifulSoup

from juscraper.core.parse_utils import clean_html, coerce_date_columns

_BLOCK_SEP = re.compile(r'<table width="100%" class="tabela_formulario">')
_CNJ_RE = re.compile(r"NUMERA\S*O \S*NICA:\s*(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})")
_PARTES_LINK_RE = re.compile(r"proc_partes_advogados2\.jsp\?listaProcessos=(\d{17})")
_SEGREDO_RE = re.compile(r"segredo de justi", re.IGNORECASE)
_OAB_RE = re.compile(r"^\w+/[A-Z]{2}$")
_NOT_FOUND_RE = re.compile(r"Nenhum processo encontrado", re.IGNORECASE)


def _field_by_id(block: str, field_id: str) -> str | None:
    m = re.search(rf'id="{field_id}"[^>]*>(.*?)</td>', block, re.DOTALL)
    return clean_html(m.group(1)) if m else None


def _field_by_label(block: str, label: str) -> str | None:
    m = re.search(
        r"<b>\s*" + re.escape(label) + r":(?:&nbsp;)?\s*</b>\s*</td>\s*<td[^>]*>(.*?)</td>",
        block,
        re.DOTALL | re.IGNORECASE,
    )
    return clean_html(m.group(1)) if m else None


def format_numero_tjmg(digits: str) -> str:
    """Formata 17 digitos no padrao ``1.0000.26.408376-7/001``."""
    return f"{digits[0]}.{digits[1:5]}.{digits[5:7]}.{digits[7:13]}-{digits[13]}/{digits[14:17]}"


def extract_partes_ids(html: str) -> list[str]:
    """Numeros TJMG (17 digitos) com link de partes/advogados, na ordem da pagina."""
    return list(dict.fromkeys(_PARTES_LINK_RE.findall(html)))


def parse_resultado(html: str) -> list[dict]:
    """Extrai um dict por recurso da pagina ``proc_resultado2.jsp``."""
    if _NOT_FOUND_RE.search(html):
        return []
    rows = []
    for block in _BLOCK_SEP.split(html)[1:]:
        cnj = _CNJ_RE.search(block)
        link = _PARTES_LINK_RE.search(block)
        interno = re.search(r"MERO TJMG:\s*(\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3})", block)
        if interno:
            processo_interno: str | None = interno.group(1)
        elif link:
            processo_interno = format_numero_tjmg(link.group(1))
        else:
            processo_interno = None
        # O aviso de segredo aparece logo apos o cabecalho, antes do proximo bloco.
        segredo = link is None and bool(_SEGREDO_RE.search(block))
        rows.append({
            "processo": cnj.group(1) if cnj else None,
            "processo_interno": processo_interno,
            "segredo_justica": segredo,
            "situacao": _field_by_id(block, "campoStatus"),
            "secretaria": _field_by_id(block, "campoSecretaria"),
            "classe": _field_by_id(block, "campoClasse"),
            "assunto": _field_by_label(block, "Assunto"),
            "orgao_julgador": _field_by_id(block, "campoCamara"),
            "data_cadastramento": _field_by_label(block, "Data Cadastramento"),
            "data_distribuicao": _field_by_label(block, "Data Distribuição"),
            "_partes_id": link.group(1) if link else None,
        })
    return rows


def parse_partes(html: str) -> list[dict]:
    """Extrai partes e advogados da pagina ``proc_partes_advogados2.jsp``."""
    soup = BeautifulSoup(html, "html.parser")
    partes = []
    for label_td in soup.find_all("td", attrs={"width": "10%", "valign": "top"}):
        content_td = label_td.find_next_sibling("td")
        if content_td is None:
            continue
        tipo = label_td.get_text(" ", strip=True).replace("\xa0", " ").strip().rstrip(":").strip()
        tipo = re.sub(r"\s*\(.*?\)", "", tipo).strip()

        advogados = []
        for tr in content_td.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) != 2:
                continue
            oab = tds[0].get_text(strip=True)
            if not _OAB_RE.match(oab):
                continue
            nome_adv = tds[1].get_text(" ", strip=True).replace("\xa0", " ")
            advogados.append({"oab": oab, "nome": re.sub(r"^-\s*", "", nome_adv).strip()})
        for t in content_td.find_all("table"):
            t.extract()

        baixa = None
        baixa_b = content_td.find("b", string=re.compile(r"Baixa"))
        if baixa_b is not None:
            baixa = (baixa_b.next_sibling or "").strip() or None
            baixa_b.extract()
        nome = content_td.get_text(" ", strip=True)
        if baixa:
            nome = nome.replace(baixa, "").strip()
        partes.append({"tipo": tipo, "nome": nome, "baixa": baixa, "advogados": advogados})
    return partes


def cposg_parse(raw: list[dict]) -> pd.DataFrame:
    """Transforma a saida de :func:`cposg_download` em DataFrame (uma linha por recurso).

    Numeros sem resultado (nao encontrados ou falha de rede) viram uma linha
    so com ``id_cnj``, para distinguir "consultado mas ausente" de
    "nunca consultado". Recursos em segredo de justica vem com
    ``segredo_justica=True`` e ``partes=None``.
    """
    rows: list[dict] = []
    for item in raw:
        recursos = parse_resultado(item["resultado"]) if item.get("resultado") else []
        if not recursos:
            rows.append({"id_cnj": item["id_cnj"]})
            continue
        for rec in recursos:
            partes_id = rec.pop("_partes_id")
            partes_html = item.get("partes", {}).get(partes_id) if partes_id else None
            rec["partes"] = parse_partes(partes_html) if partes_html else None
            rows.append({"id_cnj": item["id_cnj"], **rec})
    df = pd.DataFrame(rows)
    coerce_date_columns(df, ["data_cadastramento", "data_distribuicao"], date_format="%d/%m/%Y")
    return df
