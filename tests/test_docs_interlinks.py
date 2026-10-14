"""Gate da referência do quartodoc: papéis Sphinx em ``See Also`` e o filtro interlinks.

O quartodoc reescreve cada papel Sphinx de uma seção ``See Also``, como
``:class:`InputCJSGTJMG```, em link Markdown com o alvo entre crases:
``[](:class:`InputCJSGTJMG`)``. Quem resolve esse alvo é o filtro Lua
``interlinks``, declarado em ``docs/_quarto.yml``. Sem o filtro, o Pandoc gera
``<a href=":class:`...`"></a>``, âncora vazia que some do texto e deixa na
página só a pontuação em volta ("/ ."). Os mesmos links aparecem nas anotações
de tipo por causa de ``render_interlinks: true``.

Os testes daqui reprovam o site sem o filtro ou com o filtro antes do
``quarto`` em ``filters``, e o título ``See Also:`` fora do formato que o
griffe reconhece. O papel que a conversão do quartodoc não alcança, como o de
nome com dígito, fica com ``docs/sphinx_roles.lua`` e com o gate de
``tests/test_docs_papeis_sphinx.py``.
"""

import ast
import hashlib
import re
from collections.abc import Iterator
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
FONTE = RAIZ / "src" / "juscraper"

# O griffe compara o tipo da seção sem distinguir maiúsculas, e o quartodoc
# converte os papéis quando o título, em minúsculas, é "see also".
_TITULO_SEE_ALSO = re.compile(r"see also:\s*", re.IGNORECASE)
_LINHA_SEE_ALSO = re.compile(r"\s*see also\s*:", re.IGNORECASE)

# SHA-256 de interlinks.lua em machow/quartodoc, tag v0.11.1. Ao atualizar a
# cópia em docs/_extensions/interlinks/, trazer o arquivo da tag nova sem
# editar e trocar o hash e a tag no comentário de docs/_quarto.yml.
_SHA256_INTERLINKS_LUA = "491cc9bf90b3d0bb6eca50ba1b32dcfa87d900d44723fdd8a17af88d3108dbe6"


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


def _varrer_see_also(docstring: str) -> tuple[list[str], list[str]]:
    """Separa as seções ``See Also:`` que o griffe reconhece das que ele ignora.

    O griffe só abre a seção quando o título ocupa a linha sozinho, tem linha
    em branco acima (ou abre a docstring) e não tem linha em branco logo
    abaixo. Fora disso, o bloco vira texto comum e a seção some da
    referência, com o título colado ao texto. Devolve o corpo de cada seção
    reconhecida, que vai até a primeira linha não vazia sem recuo, e as
    linhas de título fora do formato.
    """
    linhas = docstring.splitlines()
    corpos: list[str] = []
    fora_do_formato: list[str] = []
    for i, linha in enumerate(linhas):
        if not _LINHA_SEE_ALSO.match(linha):
            continue
        linha_em_branco_acima = i == 0 or not linhas[i - 1].strip()
        linha_seguinte_com_texto = i + 1 < len(linhas) and bool(linhas[i + 1].strip())
        if not (_TITULO_SEE_ALSO.fullmatch(linha) and linha_em_branco_acima and linha_seguinte_com_texto):
            fora_do_formato.append(linha.strip())
            continue
        corpo = []
        for seguinte in linhas[i + 1 :]:
            if seguinte.strip() and not seguinte.startswith((" ", "\t")):
                break
            corpo.append(seguinte)
        corpos.append("\n".join(corpo))
    return corpos, fora_do_formato


def _varrer_fonte() -> tuple[list[str], list[str]]:
    casos = []
    fora_do_formato = []
    for caminho in sorted(FONTE.rglob("*.py")):
        relativo = caminho.relative_to(RAIZ).as_posix()
        for qualname, docstring in _docstrings(caminho):
            corpos, titulos_ruins = _varrer_see_also(docstring)
            for n, _corpo in enumerate(corpos):
                casos.append(f"{relativo}::{qualname}#{n}")
            fora_do_formato += [f"{relativo}::{qualname}: {titulo!r}" for titulo in titulos_ruins]
    return casos, fora_do_formato


CASOS_SEE_ALSO, SEE_ALSO_FORA_DO_FORMATO = _varrer_fonte()


def test_ha_secoes_see_also_para_conferir():
    # Protege o teste de formato de passar vazio se a varredura deixar de
    # reconhecer o título da seção.
    assert len(CASOS_SEE_ALSO) >= 20


def test_quarto_declara_filtro_interlinks_depois_do_quarto():
    config = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))
    filtros = config.get("filters") or []
    assert "interlinks" in filtros, (
        "docs/_quarto.yml precisa declarar o filtro `interlinks`; sem ele, os papéis "
        "Sphinx de See Also e as anotações de tipo viram <a> com href inválido."
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
    # O hash reprova cópia truncada ou editada, que o Quarto aceitaria em
    # silêncio, deixando os links quebrados de volta.
    conteudo = (extensao / "interlinks.lua").read_bytes()
    assert hashlib.sha256(conteudo).hexdigest() == _SHA256_INTERLINKS_LUA
    assert (extensao / "LICENSE").is_file()


def test_see_also_no_formato_que_o_griffe_reconhece():
    assert not SEE_ALSO_FORA_DO_FORMATO, (
        "Título `See Also:` precisa ocupar a linha sozinho, ter linha em branco acima "
        "e o conteúdo recuado logo abaixo, sem linha em branco no meio. Fora disso o "
        "griffe lê o bloco como texto e a seção não aparece na referência:\n" + "\n".join(SEE_ALSO_FORA_DO_FORMATO)
    )
