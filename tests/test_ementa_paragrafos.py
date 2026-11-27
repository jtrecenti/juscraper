r"""Ementa que chega em HTML sai com um parágrafo por linha.

Cada caso roda o parser sobre samples reais e compara a ementa de cada linha
com a de um oráculo independente, montado com o BeautifulSoup sobre o HTML
bruto: ``<br>`` e as tags de bloco separam as linhas, o resto do texto fica
como o ``get_text`` o devolve (as tags inline somem sem deixar espaço, e
comentários, ``<style>`` e ``<script>`` saem). O teste também confere quantas
ementas do caso têm ``\n`` e exige que nenhuma tenha tag, ``\r`` ou ``\xa0``.

Os testes unitários de :func:`juscraper.core.parse_utils.html_para_texto`
ficam em ``tests/core/test_parse_utils.py``.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from bs4 import BeautifulSoup

from juscraper.aggregators.falcao import parse as falcao_parse
from juscraper.core.parse_utils import normalizar_texto
from juscraper.courts.tjap import parse as tjap_parse
from juscraper.courts.tjgo import parse as tjgo_parse
from juscraper.courts.tjmg import parse as tjmg_parse
from juscraper.courts.tjmt import parse as tjmt_parse
from juscraper.courts.tjrj import parse as tjrj_parse
from juscraper.courts.tjrn import parse as tjrn_parse
from juscraper.courts.tjro import parse as tjro_parse
from juscraper.courts.tjsc import parse as tjsc_parse
from tests._helpers import load_sample_bytes

_SEPARADOR = "\x00"
_BLOCOS = (
    "address", "article", "aside", "blockquote", "body", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header",
    "hr", "html", "li", "main", "nav", "ol", "p", "pre", "section", "table",
    "tbody", "tfoot", "thead", "tr", "ul",
)
_PROIBIDOS = re.compile(r"[\r\xa0]|<[a-zA-Z/!]")
# Ementa bruta da página do TJMG, como o parser a recorta.
_TJMG_EMENTA_RE = re.compile(r"<strong>\s*Ementa:\s*</strong>(.*?)</div>", re.DOTALL | re.IGNORECASE)


def _texto(tribunal: str, arquivo: str, encoding: str = "utf-8") -> str:
    # Em bytes: ``read_text`` trocaria o ``\r\n`` literal de um sample.
    return load_sample_bytes(tribunal, arquivo).decode(encoding)


def _jsons(tribunal: str, *arquivos: str) -> list[Any]:
    return [json.loads(_texto(tribunal, arquivo)) for arquivo in arquivos]


def _htmls(tribunal: str, *arquivos: str) -> list[str]:
    return [_texto(tribunal, arquivo, "iso-8859-1") for arquivo in arquivos]


def oraculo(html: str, *, preservar_quebras: bool = False) -> str:
    """Parágrafos do HTML pelo BeautifulSoup, um por linha."""
    if preservar_quebras:
        html = re.sub(r"\r\n?|\n", "<br>", html)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["style", "script", "title"]):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with(_SEPARADOR)
    for bloco in soup.find_all(_BLOCOS):
        bloco.insert_before(_SEPARADOR)
        bloco.insert_after(_SEPARADOR)
    for celula in soup.find_all(["td", "th"]):
        celula.insert_before(" ")
        celula.insert_after(" ")
    partes = (" ".join(normalizar_texto(parte).split()) for parte in soup.get_text().split(_SEPARADOR))
    return "\n".join(parte for parte in partes if parte)


@dataclass(frozen=True)
class Caso:
    paginas: Callable[[], list[Any]]
    """Páginas brutas dos samples, lidas uma vez por caso."""
    ementas: Callable[[list[Any]], list[Any]]
    """Ementas que o parser devolve, na ordem dos documentos."""
    esperadas: Callable[[list[Any]], list[Any]]
    """Ementas do oráculo sobre o bruto, na mesma ordem."""
    com_paragrafos: int
    """Quantas ementas dos samples têm mais de um parágrafo."""


_JSON_CJSG = ("cjsg/results_normal_page_01.json", "cjsg/results_normal_page_02.json", "cjsg/single_page.json")


def _tjro() -> list[Any]:
    # O script de captura corta ``ds_modelo_documento`` em 500 caracteres e
    # acrescenta ``"..."``, às vezes no meio de uma tag ou entidade. O teste
    # descarta o trecho depois da última tag inteira.
    paginas = _jsons("tjro", *_JSON_CJSG[:2])
    for hit in (hit for pagina in paginas for hit in pagina["hits"]["hits"]):
        texto = hit["_source"]["ds_modelo_documento"]
        if texto and texto.endswith("..."):
            hit["_source"]["ds_modelo_documento"] = texto[: texto.rfind(">") + 1]
    return paginas


def _tjsc() -> list[str]:
    return _htmls("tjsc", "cjsg/results_normal_page_01.html", "cjsg/results_normal_page_02.html")


def _tjsc_ementas_brutas(paginas: list[str]) -> list[str]:
    soup = BeautifulSoup("".join(paginas), "html.parser")
    valores = soup.select("div.resultadoItem div.resValue.completo[id$='-EMENTA']")
    return [valor.decode_contents() for valor in valores]


def _tjgo() -> list[str]:
    return _htmls(
        "tjgo", "cjsg/results_normal_page_01.html", "cjsg/results_normal_page_02.html",
        "cjsg/results_julgado_em_page_01.html", "cjsg/single_page.html",
    )


def _tjgo_textos_brutos(paginas: list[str]) -> list[str]:
    soup = BeautifulSoup("".join(paginas), "html.parser")
    return [p.decode_contents() for p in soup.select("div.search-result p.conteudoTexto")]


def _tjrj() -> list[Any]:
    arquivos = ("xhr_page_01.json", "xhr_page_02.json", "xhr_single_page.json", "xhr_turma_recursal.json")
    return [pagina["d"] for pagina in _jsons("tjrj", *(f"cjsg/{arquivo}" for arquivo in arquivos))]


def _tjmg_esperada(html: str) -> str:
    return re.sub(r"^EMENTA:\s*", "", oraculo(html), flags=re.IGNORECASE)


def _falcao() -> Any:
    return _jsons("falcao", "pesquisa/acordaos_ementa_inteira.json")[0]


def _hits(paginas: list[Any], campo: str) -> list[Any]:
    return [hit["_source"].get(campo) for pagina in paginas for hit in pagina["hits"]["hits"]]


CASOS = {
    "tjrn-cjsg": Caso(
        lambda: _jsons("tjrn", *_JSON_CJSG),
        lambda paginas: list(tjrn_parse.cjsg_parse_manager(paginas)["ementa"]),
        lambda paginas: [oraculo(e) for e in _hits(paginas, "ementa")],
        com_paragrafos=30,
    ),
    "tjro-cjsg": Caso(
        _tjro,
        lambda paginas: list(tjro_parse.cjsg_parse_manager(paginas)["ementa"]),
        lambda paginas: [oraculo(e) for e in _hits(paginas, "ds_modelo_documento")],
        com_paragrafos=5,
    ),
    "tjap-cjsg": Caso(
        lambda: _jsons("tjap", *_JSON_CJSG),
        lambda paginas: list(tjap_parse.cjsg_parse_manager(paginas)["ementa"]),
        lambda paginas: [oraculo(i["ementa"]) for p in paginas for i in p["dados"]],
        com_paragrafos=40,
    ),
    "tjmg-cjsg": Caso(
        lambda: _htmls(
            "tjmg", "cjsg/results_normal_page_01.html", "cjsg/results_normal_page_02.html",
            "cjsg/categorizada_acordaos_page_01.html",
        ),
        lambda paginas: list(tjmg_parse.cjsg_parse(paginas)["ementa"]),
        lambda paginas: [_tjmg_esperada(m.group(1)) for p in paginas for m in _TJMG_EMENTA_RE.finditer(p)],
        com_paragrafos=16,
    ),
    "tjmt-cjsg": Caso(
        lambda: _jsons("tjmt", "cjsg/results_normal_page_01.json", "cjsg/single_page.json", "cjsg/filtro_classe.json"),
        lambda paginas: [r["ementa"] for r in tjmt_parse.cjsg_parse(paginas)],
        lambda paginas: [
            oraculo(i["conteudo"], preservar_quebras=True) for p in paginas for i in p["value"]["resultados"]
        ],
        com_paragrafos=4,
    ),
    "tjsc-cjsg": Caso(
        _tjsc,
        lambda paginas: list(tjsc_parse.cjsg_parse_manager(paginas)["ementa"]),
        lambda paginas: [oraculo(e, preservar_quebras=True) for e in _tjsc_ementas_brutas(paginas)],
        com_paragrafos=20,
    ),
    # O portal separa os parágrafos com ``\n``, sem HTML; as linhas vazias saem.
    "tjrj-cjsg": Caso(
        _tjrj,
        lambda paginas: list(tjrj_parse.cjsg_parse(paginas)["ementa"]),
        lambda paginas: [
            oraculo(d.get("TextoSemFormat") or d.get("Texto") or "", preservar_quebras=True)
            for p in paginas
            for d in p["DocumentosConsulta"]
        ],
        com_paragrafos=19,
    ),
    # Coluna ``texto``: o TJGO não tem ``ementa``. O portal manda o texto numa linha só.
    "tjgo-cjsg": Caso(
        _tjgo,
        lambda paginas: list(tjgo_parse.cjsg_parse(paginas)["texto"]),
        lambda paginas: [oraculo(t) for t in _tjgo_textos_brutos(paginas)],
        com_paragrafos=0,
    ),
    "falcao-listar_decisoes": Caso(
        lambda: [_falcao()],
        lambda paginas: [d["ementa"] for d in falcao_parse.parse_documentos(paginas[0], "acordaos")],
        lambda paginas: [oraculo(d["ementa"]) or None for d in paginas[0]["documentos"]],
        com_paragrafos=1,
    ),
}


@pytest.mark.parametrize("caso", CASOS.values(), ids=CASOS.keys())
def test_ementa_html_sai_com_um_paragrafo_por_linha(caso):
    paginas = caso.paginas()
    ementas = caso.ementas(paginas)

    assert ementas == caso.esperadas(paginas)
    assert sum("\n" in e for e in ementas if isinstance(e, str)) == caso.com_paragrafos
    assert not any(_PROIBIDOS.search(e) for e in ementas if isinstance(e, str))


def test_tjsc_ementa_nao_recebe_a_decisao():
    """A DECISÃO repetida (versão recortada e completa) não desloca os rótulos seguintes."""
    df = tjsc_parse.cjsg_parse_manager(_tjsc())

    assert df["ementa"].iloc[0].startswith("DIREITO CIVIL. RECURSO INOMINADO.")
    assert df["decisao"].iloc[0].startswith("Vistos e relatados estes autos")
    assert not (df["ementa"] == df["decisao"]).any()


def test_falcao_quebra_do_codigo_fonte_nao_separa_paragrafo():
    """No documento HTML do Falcão, a linha quebrada no meio da frase vira espaço."""
    bruta = _falcao()["documentos"][0]["ementa"]
    assert "<style" in bruta
    assert re.search(r"[a-z] *\n\s*[a-z]", bruta)

    ementa = falcao_parse.parse_documentos(_falcao(), "acordaos")[0]["ementa"]

    assert "\n" not in ementa
    assert "{" not in ementa


def test_oraculo_le_paragrafos_e_br():
    assert oraculo("<p>a <b>b</b>.</p>\n<p>c<br/>d &amp; e</p>") == "a b.\nc\nd & e"
