"""Gate da referência do quartodoc: papéis Sphinx em ``See also`` e o filtro interlinks.

O quartodoc reescreve cada papel Sphinx de uma seção ``See also``, como
``:class:`InputCJSGTJMG```, em link Markdown com o alvo entre crases:
``[](:class:`InputCJSGTJMG`)``. Quem resolve esse alvo é o filtro Lua
``interlinks``, declarado em ``docs/_quarto.yml``. Sem o filtro, o Pandoc gera
``<a href=":class:`...`"></a>``, âncora vazia que some do texto e deixa na
página só a pontuação em volta ("/ ."). Os mesmos links aparecem nas anotações
de tipo por causa de ``render_interlinks: true``.

Os testes daqui reprovam o site sem o filtro ou com o filtro antes do
``quarto`` em ``filters``, e o papel que a conversão do quartodoc não alcança,
que sai na página como texto cru ``:class:`` seguido do nome.
"""

import ast
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
FONTE = RAIZ / "src" / "juscraper"

# Cópia da expressão de ``quartodoc.renderers.base.convert_rst_link_to_md``
# (quartodoc 0.11.1). Fica copiada porque o quartodoc só entra com o extra
# ``docs`` e este gate precisa rodar no ambiente ``dev``;
# ``test_regex_igual_a_do_quartodoc`` reprova a cópia quando a original muda.
# O nome aceita só letras, ponto, sublinhado e ``~``: um dígito, como em
# ``InputCJSGTRF5``, deixa o papel inteiro fora da conversão.
_PAPEL_CONVERTIDO = re.compile(r"((:external(\+[a-zA-Z\._]+))?(:[a-zA-Z\._]+)?:[a-zA-Z\._]+:`~?[a-zA-Z\._]+`)")
_LINK_GERADO = re.compile(r"\[\]\([^)]*\)")
_PAPEL_RESTANTE = re.compile(r":[a-zA-Z_+.]+:`")
_TITULO_SEE_ALSO = re.compile(r"See [Aa]lso:\s*")


def _converter_como_quartodoc(texto: str) -> str:
    return _PAPEL_CONVERTIDO.sub(r"[](\1)", texto)


def _docstrings(caminho: Path) -> Iterator[tuple[str, str]]:
    """Gera ``(qualname, docstring)`` do módulo e de cada classe e função."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))

    def percorrer(no: ast.AST, prefixo: str) -> Iterator[tuple[str, str]]:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                nome = f"{prefixo}{filho.name}"
                texto = ast.get_docstring(filho)
                if texto:
                    yield nome, texto
                yield from percorrer(filho, f"{nome}.")

    texto_modulo = ast.get_docstring(arvore)
    if texto_modulo:
        yield "<módulo>", texto_modulo
    yield from percorrer(arvore, "")


def _secoes_see_also(docstring: str) -> Iterator[str]:
    """Gera o corpo de cada seção ``See also:`` no estilo Google.

    O corpo vai até a primeira linha não vazia sem recuo, que é onde o griffe
    encerra a seção.
    """
    linhas = docstring.splitlines()
    for i, linha in enumerate(linhas):
        if not _TITULO_SEE_ALSO.fullmatch(linha):
            continue
        corpo = []
        for seguinte in linhas[i + 1 :]:
            if seguinte.strip() and not seguinte.startswith((" ", "\t")):
                break
            corpo.append(seguinte)
        yield "\n".join(corpo)


def _casos_see_also() -> list:
    casos = []
    for caminho in sorted(FONTE.rglob("*.py")):
        relativo = caminho.relative_to(RAIZ).as_posix()
        for qualname, docstring in _docstrings(caminho):
            for n, corpo in enumerate(_secoes_see_also(docstring)):
                casos.append(pytest.param(corpo, id=f"{relativo}::{qualname}#{n}"))
    return casos


CASOS_SEE_ALSO = _casos_see_also()


def test_ha_secoes_see_also_para_conferir():
    # Protege o teste parametrizado abaixo de passar vazio se a varredura
    # deixar de reconhecer o título da seção.
    assert len(CASOS_SEE_ALSO) >= 20


def test_quarto_declara_filtro_interlinks_depois_do_quarto():
    config = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))
    filtros = config.get("filters") or []
    assert "interlinks" in filtros, (
        "docs/_quarto.yml precisa declarar o filtro `interlinks`; sem ele, os papéis "
        "Sphinx de See also e as anotações de tipo viram <a> com href inválido."
    )
    # Antes do `quarto`, o filtro troca os tipos por código antes de o Quarto
    # decidir as larguras das tabelas, e as tabelas de parâmetros passam a usar
    # larguras calculadas sobre o Markdown cru (ver o comentário em _quarto.yml).
    assert "quarto" in filtros, "docs/_quarto.yml precisa listar `quarto` em `filters`, antes de `interlinks`."
    assert filtros.index("quarto") < filtros.index("interlinks"), (
        "Em docs/_quarto.yml, `interlinks` precisa vir depois de `quarto` em `filters`."
    )


def test_extensao_interlinks_presente():
    extensao = DOCS / "_extensions" / "interlinks"
    manifesto = yaml.safe_load((extensao / "_extension.yml").read_text(encoding="utf-8"))
    filtros = manifesto["contributes"]["filters"]
    assert filtros == ["interlinks.lua"]
    assert (extensao / "interlinks.lua").is_file()


@pytest.mark.parametrize("corpo", CASOS_SEE_ALSO)
def test_papeis_em_see_also_sao_convertidos_pelo_quartodoc(corpo):
    sem_links = _LINK_GERADO.sub("", _converter_como_quartodoc(corpo))
    assert not _PAPEL_RESTANTE.search(sem_links), (
        "Papel Sphinx que o quartodoc não converte em link sai cru na referência. "
        "O nome aceita só letras, ponto, sublinhado e `~`; sem dígito. Use "
        "``Nome`` (literal) para um nome com dígito. Trecho:\n" + corpo
    )


@pytest.mark.parametrize(
    "texto",
    [
        ":class:`InputCJSGTJMG`",
        ":class:`~juscraper.courts.tjsp.schemas.InputCJSGTJSP`",
        ":meth:`listar_processos` — texto depois do papel",
        ":py:func:`juscraper.scraper`",
        ":external+python:py:class:`str`",
        ":class:`InputCJSGTRF5`",
        "``InputCJSGTRF5``",
    ],
)
def test_regex_igual_a_do_quartodoc(texto):
    base = pytest.importorskip("quartodoc.renderers.base")
    assert _converter_como_quartodoc(texto) == base.convert_rst_link_to_md(texto)
