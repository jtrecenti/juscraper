"""Gate dos papéis Sphinx fora de ``See Also`` na referência do quartodoc.

O quartodoc só converte papéis Sphinx dentro de ``See Also``. Em qualquer
outra seção (resumo, descrição de parâmetro, de exceção ou de retorno, nota,
bloco de texto livre), o Markdown lê ``:meth:`cjsg``` como o texto ``:meth:``
colado ao código ``cjsg``, e a página mostra o papel cru. Quem resolve isso é
``docs/sphinx_roles.lua``, declarado em ``docs/_quarto.yml`` entre ``quarto`` e
``interlinks``: ele troca o par por um link igual ao que o quartodoc escreve em
``See Also``, e o ``interlinks`` o resolve. Nos dois tipos de link, o
``:meth:`` passa a ``:function:``, o papel com que o inventário registra
métodos, e o nome curto é qualificado pela classe da página, como no Sphinx,
para virar link para o método.

O filtro só reconhece o papel quando o nome dele está na tabela ``ROLES`` do
Lua e quando nada de letra ASCII, dígito ou sublinhado vem colado antes; fora
disso, o papel sai cru. O alvo também não pode ter título explícito nem
dois-pontos, que o ``interlinks`` não interpreta: o papel some, mas a página
mostra código com o texto errado ou vazio. Os testes daqui reprovam o
``_quarto.yml`` sem o filtro ou com o filtro fora de ordem, e qualquer
docstring do pacote, de módulo, classe, função ou atributo, com papel num
desses casos.
"""

import ast
import importlib
import inspect
import json
import re
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

from tests.test_docs_interlinks import _docstrings

RAIZ = Path(__file__).resolve().parents[1]
DOCS = RAIZ / "docs"
FONTE = RAIZ / "src" / "juscraper"
FILTRO = DOCS / "sphinx_roles.lua"

# Trecho de código Markdown: sequência de crases, conteúdo, a mesma sequência.
_TRECHO_DE_CODIGO = re.compile(r"(`+)(.+?)\1", re.DOTALL)
# O que o Pandoc lê como um único ``Str`` colado ao código: o texto sem
# espaço nem crase que vem imediatamente antes dele.
_TOKEN_ANTES = re.compile(r"[^\s`]*\Z")
# Token que termina como papel Sphinx (``:meth:``, ``:py:class:``): na página,
# sai como o próprio papel seguido do nome em código, se o filtro não o pegar.
_PARECE_PAPEL = re.compile(r":[A-Za-z][\w+.]*:\Z")
# Espelho de ``split_role`` em sphinx_roles.lua. ``%w`` do Lua é letra ou
# dígito ASCII (um caractere acentuado não conta), e ``.-`` é o ``*?`` do
# Python.
_SEPARA_PAPEL = re.compile(r"(.*?)(:[A-Za-z0-9_+.:]*:)", re.DOTALL)


def _papeis_do_filtro() -> set[str]:
    """Lê a tabela ``ROLES`` do filtro, fonte única dos papéis aceitos."""
    texto = FILTRO.read_text(encoding="utf-8")
    bloco = re.search(r"local ROLES = \{(.*?)\}", texto, re.DOTALL)
    assert bloco, "docs/sphinx_roles.lua não define mais a tabela ROLES."
    return set(re.findall(r"(\w+) = true", bloco.group(1)))


PAPEIS = _papeis_do_filtro()


def _separar_papel(token: str) -> tuple[str, str] | None:
    """Reproduz ``split_role``: devolve ``(prefixo, papel)`` ou ``None``."""
    casamento = _SEPARA_PAPEL.fullmatch(token)
    if casamento is None:
        return None
    prefixo, papel = casamento.groups()
    ultimo = re.search(r":([A-Za-z]+):\Z", papel)
    if ultimo is None or ultimo.group(1) not in PAPEIS:
        return None
    if re.search(r"[A-Za-z0-9_]\Z", prefixo):
        return None
    return prefixo, papel


def _pares(texto: str):
    """Gera ``(token, codigo)`` para cada trecho de código com texto colado antes."""
    for trecho in _TRECHO_DE_CODIGO.finditer(texto):
        token = _TOKEN_ANTES.search(texto, 0, trecho.start())
        assert token is not None  # o padrão aceita a cadeia vazia
        yield token.group(0), trecho.group(2)


# Cabeçalho de nível 1 que abre cada página do quartodoc, com o caminho
# completo do objeto como identificador, em qualquer posição do atributo.
_CABECALHO_DA_PAGINA = re.compile(r"\A# [^\n]*\{[^}\n]*#(juscraper\.[^\s}]+)[^}\n]*\}")
# Link Markdown cujo alvo é um papel entre crases. O quartodoc escreve em See
# Also o link vazio, ``[](:meth:`cjsg`)``, o único que o filtro reescreve.
_LINK_COM_PAPEL = re.compile(r"\[([^\]]*)\]\((:[A-Za-z0-9_+.:]*:)`([^`]*)`\)")


def _alvo_de_metodo(papel: str, nome: str, pagina: str | None) -> tuple[str, str]:
    """Espelho de ``method_target``: reescreve ``:meth:``; outros papéis passam."""
    if not papel.endswith(":meth:"):
        return papel, nome
    papel = papel.removesuffix("meth:") + "function:"
    curto = nome.removeprefix("~")
    if pagina is not None and "." not in curto:
        nome = f"~{pagina}.{curto}"
    return papel, nome


def _alvos_pelo_espelho(texto: str) -> list[str]:
    """Alvos de link que o filtro deixaria no documento, segundo o espelho em Python."""
    cabecalho = _CABECALHO_DA_PAGINA.match(texto)
    pagina = cabecalho.group(1) if cabecalho else None
    alvos: list[tuple[int, str]] = []
    trechos_de_link = []
    for link in _LINK_COM_PAPEL.finditer(texto):
        trechos_de_link.append(link.span())
        papel, nome = link.group(2), link.group(3)
        if not link.group(1):
            papel, nome = _alvo_de_metodo(papel, nome, pagina)
        alvos.append((link.start(), f"{papel}%60{nome}%60"))
    for trecho in _TRECHO_DE_CODIGO.finditer(texto):
        # o código dentro do alvo de um link não é ``Code`` para o Pandoc
        if any(inicio <= trecho.start() < fim for inicio, fim in trechos_de_link):
            continue
        token = _TOKEN_ANTES.search(texto, 0, trecho.start())
        assert token is not None  # o padrão aceita a cadeia vazia
        separado = _separar_papel(token.group(0))
        if separado is not None:
            papel, nome = _alvo_de_metodo(separado[1], trecho.group(2), pagina)
            alvos.append((trecho.start(), f"{papel}%60{nome}%60"))
    return [alvo for _, alvo in sorted(alvos)]


def _alvos_pelo_filtro(texto: str) -> list[str]:
    """Alvos de link que o filtro Lua cria, rodando-o no Pandoc do Quarto."""
    saida = subprocess.run(
        ["quarto", "pandoc", "-f", "markdown", "-t", "json", "--lua-filter", str(FILTRO)],
        input=texto,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    alvos: list[str] = []

    def percorrer(no):
        if isinstance(no, dict):
            if no.get("t") == "Link":
                alvos.append(no["c"][2][0])
            for valor in no.values():
                percorrer(valor)
        elif isinstance(no, list):
            for item in no:
                percorrer(item)

    percorrer(json.loads(saida))
    return alvos


def _defeito(token: str, codigo: str) -> str | None:
    """Diz por que o papel ``token`` + ``codigo`` sairia errado na página, ou ``None``."""
    if _separar_papel(token) is None:
        return "o filtro não reconhece o papel, que sai cru"
    if "<" in codigo and codigo.rstrip().endswith(">"):
        return "título explícito, que sai como código com o texto todo"
    # O ``interlinks`` parte o alvo nos dois-pontos para separar papel e nome;
    # um nome com ``:`` chega partido e a página mostra código vazio.
    if ":" in codigo or not codigo.strip():
        return "nome com dois-pontos ou vazio, que sai como código vazio"
    return None


def _docstrings_de_atributo(caminho: Path) -> Iterator[tuple[str, str]]:
    """Gera ``(qualname, docstring)`` das constantes e atributos documentados.

    ``_docstrings`` lê só módulo, classe e função; a docstring de atributo é a
    string solta logo depois da atribuição, que o griffe também publica.
    """
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))

    def percorrer(corpo: list[ast.stmt], prefixo: str) -> Iterator[tuple[str, str]]:
        for i, no in enumerate(corpo):
            if isinstance(no, ast.ClassDef):
                yield from percorrer(no.body, f"{prefixo}{no.name}.")
                continue
            alvo: ast.expr | None = no.target if isinstance(no, ast.AnnAssign) else None
            if isinstance(no, ast.Assign) and len(no.targets) == 1:
                alvo = no.targets[0]
            seguinte = corpo[i + 1] if i + 1 < len(corpo) else None
            if (
                isinstance(alvo, ast.Name)
                and isinstance(seguinte, ast.Expr)
                and isinstance(seguinte.value, ast.Constant)
                and isinstance(seguinte.value.value, str)
            ):
                yield f"{prefixo}{alvo.id}", inspect.cleandoc(seguinte.value.value)

    yield from percorrer(arvore.body, "")


def _varrer_fonte() -> tuple[int, list[str]]:
    """Conta os papéis das docstrings do pacote e lista os que sairiam errados."""
    total = 0
    errados = []
    for caminho in sorted(FONTE.rglob("*.py")):
        relativo = caminho.relative_to(RAIZ).as_posix()
        for qualname, docstring in [*_docstrings(caminho), *_docstrings_de_atributo(caminho)]:
            for token, codigo in _pares(docstring):
                if not _PARECE_PAPEL.search(token):
                    continue
                total += 1
                defeito = _defeito(token, codigo)
                if defeito is not None:
                    errados.append(f"{relativo}::{qualname}: {token}`{codigo}` ({defeito})")
    return total, errados


TOTAL_PAPEIS, PAPEIS_CRUS = _varrer_fonte()

_METH_CURTO = re.compile(r":(?:py:)?meth:`~?([^`.]+)`")


def _classes_publicadas() -> list[type]:
    """Classes que ``docs/_quarto.yml`` manda o quartodoc documentar."""
    config = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))["quartodoc"]
    classes = []
    for secao in config["sections"]:
        for alvo in secao["contents"]:
            modulo, _, nome = f"juscraper.{alvo}".rpartition(".")
            objeto = getattr(importlib.import_module(modulo), nome)
            if isinstance(objeto, type):
                classes.append(objeto)
    return classes


def _meth_curto_sem_metodo() -> tuple[int, list[str]]:
    """Confere cada ``:meth:`` curto das docstrings que a página da classe mostra.

    O filtro qualifica o nome curto pela classe da página, e o ``interlinks`` só
    acha o método se ele for membro público da própria classe, que o quartodoc
    documenta; herdado ou privado sai como código, sem aviso no build. A página
    mostra a docstring da classe e a dos métodos públicos dela, não a do
    ``__init__``.
    """
    total = 0
    sem_metodo = []
    for classe in _classes_publicadas():
        membros = {nome: valor for nome, valor in vars(classe).items() if not nome.startswith("_")}
        docstrings = [("", classe.__doc__)]
        docstrings += [(f".{nome}", getattr(valor, "__doc__", None)) for nome, valor in membros.items()]
        for sufixo, docstring in docstrings:
            for citado in _METH_CURTO.findall(docstring or ""):
                total += 1
                if citado not in membros:
                    sem_metodo.append(f"{classe.__module__}.{classe.__qualname__}{sufixo}: :meth:`{citado}`")
    return total, sem_metodo


def test_quarto_declara_filtro_de_papeis_entre_quarto_e_interlinks():
    config = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))
    filtros = config.get("filters") or []
    assert "sphinx_roles.lua" in filtros, (
        "docs/_quarto.yml precisa declarar `sphinx_roles.lua` em `filters`; sem ele, "
        "papel Sphinx fora de See Also sai cru na referência, como `:meth:` seguido do nome."
    )
    # Depois de `interlinks`, o link criado pelo filtro não seria resolvido e
    # viraria âncora com href inválido; antes de `quarto`, mudaria a largura das
    # tabelas (ver o comentário em docs/_quarto.yml).
    assert filtros.index("quarto") < filtros.index("sphinx_roles.lua") < filtros.index("interlinks"), (
        "Em docs/_quarto.yml, `sphinx_roles.lua` precisa vir depois de `quarto` e antes de `interlinks`."
    )


def test_ha_papeis_para_conferir():
    # Protege o gate de passar vazio se a varredura deixar de achar papéis.
    assert {"class", "meth", "func"} <= PAPEIS
    assert TOTAL_PAPEIS >= 500


def test_papeis_das_docstrings_no_formato_que_o_filtro_converte():
    assert not PAPEIS_CRUS, (
        "Papel Sphinx que sairia errado na referência. O filtro docs/sphinx_roles.lua "
        f"aceita os papéis {sorted(PAPEIS)}, sem letra ASCII, dígito ou sublinhado colado "
        "antes, e o alvo não pode ter título explícito (`:meth:`texto <alvo>``) nem "
        "dois-pontos. Use um desses papéis ou escreva o nome como literal, ``nome``:\n"
        + "\n".join(PAPEIS_CRUS)
    )


def test_meth_curto_cita_metodo_publico_da_propria_classe():
    total, sem_metodo = _meth_curto_sem_metodo()
    assert total >= 50  # protege o gate de passar vazio
    assert not sem_metodo, (
        "`:meth:` com nome curto vira link para o método da classe da página só "
        "quando o método é público e definido na própria classe; senão sai como "
        "código. Use o caminho completo de onde o método é documentado:\n" + "\n".join(sem_metodo)
    )


def test_docstrings_de_atributo_entram_na_varredura():
    # core/failures.py documenta constantes com :data:; sem a leitura das
    # docstrings de atributo, papel errado numa delas passaria pelo gate.
    docstrings = dict(_docstrings_de_atributo(FONTE / "core" / "failures.py"))
    assert ":data:`COLUNA_MOTIVO_FALHA`" in docstrings["MOTIVOS_FALHA"]


@pytest.mark.parametrize(
    ("token", "codigo", "errado"),
    [
        pytest.param(":meth:", "cjsg", False, id="papel-valido"),
        pytest.param("(:py:class:", "~a.B", False, id="parentese-dominio-til"),
        pytest.param(":ref:", "secao", True, id="papel-fora-da-tabela"),
        pytest.param("schema:class:", "X", True, id="colado-a-palavra"),
        pytest.param(":meth:", "texto <juscraper.scraper>", True, id="titulo-explicito"),
        pytest.param(":data:", "a:b", True, id="dois-pontos-no-nome"),
        pytest.param("é:meth:", "cjsg", False, id="letra-acentuada-colada"),
    ],
)
def test_defeito_classifica_cada_forma(token, codigo, errado):
    assert (_defeito(token, codigo) is not None) is errado


_PAGINA = "# courts.tjmg.client.TJMGScraper { #juscraper.courts.tjmg.client.TJMGScraper }\n\n"
_METODO = "juscraper.courts.tjmg.client.TJMGScraper"

AMOSTRAS = [
    pytest.param("x :meth:`cjsg` e", [":function:%60cjsg%60"], id="meth-sem-pagina"),
    pytest.param("(ver :class:`~a.B`).", [":class:%60~a.B%60"], id="parentese-e-til"),
    pytest.param("schema :py:class:`InputCJSGTRF3`.", [":py:class:%60InputCJSGTRF3%60"], id="dominio-e-digito"),
    pytest.param("| a | b |\n|---|---|\n| x | ver :func:`f` |\n", [":func:%60f%60"], id="celula-de-tabela"),
    pytest.param("Default:`x` e `z` solto.", [], id="palavra-com-dois-pontos"),
    pytest.param("schema:class:`X` colado.", [], id="papel-colado-a-palavra"),
    pytest.param("veja :ref:`secao`.", [], id="papel-fora-da-tabela"),
    pytest.param("é:meth:`cjsg`", [":function:%60cjsg%60"], id="letra-acentuada-colada"),
    pytest.param(_PAGINA + "ver :meth:`cjsg`.", [f":function:%60~{_METODO}.cjsg%60"], id="meth-curto-na-pagina"),
    pytest.param(
        _PAGINA + "ver :py:meth:`~cpopg`.", [f":py:function:%60~{_METODO}.cpopg%60"], id="meth-dominio-e-til"
    ),
    pytest.param(_PAGINA + "ver :meth:`Base.cjsg`.", [":function:%60Base.cjsg%60"], id="meth-com-ponto"),
    pytest.param(_PAGINA + "ver :class:`X`.", [":class:%60X%60"], id="class-na-pagina"),
    pytest.param(
        _PAGINA + "[](:meth:`cposg`) e [](:class:`Y`).",
        [f":function:%60~{_METODO}.cposg%60", ":class:%60Y%60"],
        id="links-do-see-also",
    ),
    pytest.param("# Título { #outro }\n\nver :meth:`cjsg`.", [":function:%60cjsg%60"], id="pagina-fora-do-pacote"),
    pytest.param(
        "intro\n\n" + _PAGINA + "ver :meth:`cjsg`.", [":function:%60cjsg%60"], id="cabecalho-depois-de-texto"
    ),
    pytest.param(
        "# x {#juscraper.a.B .classe}\n\nver :meth:`cjsg`.",
        [":function:%60~juscraper.a.B.cjsg%60"],
        id="atributo-sem-espaco-e-com-classe",
    ),
    pytest.param(
        _PAGINA + "[texto](:meth:`cposg`) e [](:meth:`cjsg`).",
        [":meth:%60cposg%60", f":function:%60~{_METODO}.cjsg%60"],
        id="link-com-texto-fica",
    ),
    pytest.param(
        _PAGINA + "# Outro { #juscraper.a.B }\n\nver :meth:`cjsg`.",
        [f":function:%60~{_METODO}.cjsg%60"],
        id="vale-o-primeiro-cabecalho",
    ),
]


@pytest.mark.parametrize(("texto", "esperado"), AMOSTRAS)
def test_espelho_python_do_filtro(texto, esperado):
    assert _alvos_pelo_espelho(texto) == esperado


@pytest.mark.parametrize(("texto", "esperado"), AMOSTRAS)
def test_filtro_lua_converte_como_o_espelho(texto, esperado):
    # O gate das docstrings confia no espelho; este teste prende o espelho ao
    # comportamento real do filtro quando o Quarto está instalado.
    if shutil.which("quarto") is None:
        pytest.skip("quarto não está no PATH")
    assert _alvos_pelo_filtro(texto) == esperado
