"""Reprova docstrings que o parser Google do griffe lê diferente do pretendido.

O quartodoc usa esse parser, e o ``quartodoc build`` passa mesmo quando ele lê
errado; o defeito só aparece na referência publicada. O teste reprova aviso de
falha do par ``nome: descrição`` (lista de exceções ou de nomes partida em duas
linhas), entrada de ``Raises:`` com várias exceções, ``Returns:`` que o griffe
lê com itens a mais, sem tipo, com o tipo repetido ou com tipo diferente da
assinatura, entrada de ``Args:`` com tipo escrito em parâmetro anotado (o
tipo da docstring se sobrepõe à anotação), a seção ``Warns:``, que derruba
o build, e seção no estilo numpy (título sublinhado por ``---``), que o parser
Google publica como texto, sem a tabela de parâmetros. Os casos e as formas
certas estão no CONTRIBUTING, em "Docstrings de métodos públicos com kwargs".

Cada módulo é lido com ``griffe.visit``, sem importar o pacote, para que a
anotação de retorno da assinatura esteja disponível e módulos fora da
referência, como os de ``core/``, também sejam conferidos.
"""

import logging
import re
from pathlib import Path

import griffe
import pytest

from tests.test_docstring_examples import RAIZ_PACOTE

_FALHA_DE_PAR = "Failed to get '"
# Um tipo (``pd.DataFrame``, ``dict[str, Any]``, ``str | None``) seguido de dois-pontos.
_TIPO = r"[A-Za-z_][\w.]*(?:\[[^:]*\])?"
_PREFIXO_DE_TIPO = re.compile(rf"^({_TIPO}(?:\s*\|\s*{_TIPO})*):(?:\s|$)")
# Título de seção numpy: uma linha de texto e, logo abaixo, uma linha só de ``-``.
# Item de lista em Markdown: ``*``, ``-`` ou ``+`` seguido de espaço.
_ITEM_DE_LISTA = re.compile(r"^\s*[*+-]\s+\S")
_SECAO_NUMPY = re.compile(r"^[ \t]*(\S[^\n]*?)[ \t]*\n[ \t]*-{3,}[ \t]*$", re.MULTILINE)


class _Coletor(logging.Handler):
    """Guarda os avisos que o griffe registra enquanto lê as docstrings."""

    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.mensagens: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.mensagens.append(record.getMessage())


def _objetos(objeto: griffe.Object):
    yield objeto
    for membro in objeto.members.values():
        if not membro.is_alias:
            yield from _objetos(membro)


def _motivo_do_estilo_numpy(docstring: str) -> str | None:
    titulos = _SECAO_NUMPY.findall(docstring)
    if titulos:
        return (
            f"seção no estilo numpy ({', '.join(titulos)}), que a referência publica como texto;"
            " escrever no estilo Google ('Args:', 'Returns:', 'Raises:')"
        )
    return None


def _motivo_da_lista_colada(texto: str) -> str | None:
    """Item de lista logo abaixo de uma linha de texto, sem linha em branco entre os dois.

    O Pandoc só abre a lista depois de linha em branco: colada ao texto, ela
    vira parte do parágrafo, com os ``*`` no meio da frase. É o que acontece
    com um título que o griffe não reconhece como seção, como ``Aliases
    deprecados (popados com ...):``, cujo bloco fica como texto corrido.
    """
    na_lista = False
    anterior = ""
    for linha in texto.splitlines():
        if not linha.strip():
            na_lista = False
        elif _ITEM_DE_LISTA.match(linha):
            if not na_lista and anterior.strip():
                return (
                    f"lista colada ao texto ({anterior.strip()!r}), que a referência publica como parágrafo;"
                    " deixar uma linha em branco antes ou usar título de seção que o griffe reconhece,"
                    " como 'Aliases deprecados:'"
                )
            na_lista = True
        anterior = linha
    return None


def _motivo_da_secao(objeto: griffe.Object, secao: griffe.DocstringSection) -> str | None:
    if isinstance(secao, (griffe.DocstringSectionText, griffe.DocstringSectionAdmonition)):
        texto = secao.value if isinstance(secao, griffe.DocstringSectionText) else secao.value.contents
        return _motivo_da_lista_colada(texto)
    if isinstance(secao, griffe.DocstringSectionWarns):
        return "seção 'Warns:', que derruba o quartodoc build; usar 'Avisos:'"
    if isinstance(secao, griffe.DocstringSectionRaises):
        grupos = [str(excecao.annotation) for excecao in secao.value if "," in str(excecao.annotation)]
        if grupos:
            return f"Raises com várias exceções numa entrada ({'; '.join(grupos)}); usar uma por entrada"
    if isinstance(secao, griffe.DocstringSectionReturns):
        return _motivo_dos_retornos(objeto, secao.value)
    if isinstance(secao, griffe.DocstringSectionParameters):
        return _motivo_dos_parametros(objeto, secao.value)
    return None


def _motivo_dos_parametros(objeto: griffe.Object, entradas: list[griffe.DocstringParameter]) -> str | None:
    # Função ou classe (os parâmetros do ``__init__``); módulo e atributo não têm.
    anotacoes = {parametro.name: parametro.annotation for parametro in getattr(objeto, "parameters", None) or []}
    copiados, agrupados = [], []
    for entrada in entradas:
        # ``a, b`` fica fora da assinatura para o griffe, que não lhe dá a anotação.
        nomes = [nome.strip().lstrip("*") for nome in entrada.name.split(",")]
        if len(nomes) > 1 and any(anotacoes.get(nome) is not None for nome in nomes):
            agrupados.append(entrada.name)
            continue
        anotacao = anotacoes.get(nomes[0])
        # Sem tipo na docstring, o griffe põe na entrada o próprio objeto da
        # anotação; outro objeto é o tipo escrito entre parênteses.
        if anotacao is not None and entrada.annotation is not anotacao:
            copiados.append(f"{entrada.name} ({entrada.annotation})")
    if agrupados:
        return (
            f"Args com parâmetros anotados numa entrada só ({'; '.join(agrupados)});"
            " uma entrada por parâmetro, sem tipo, para a referência usar a anotação"
        )
    if copiados:
        return (
            f"Args com tipo escrito em parâmetro anotado ({'; '.join(copiados)});"
            " tirar os parênteses: a referência usa a anotação da assinatura"
        )
    return None


def _itens_esperados(objeto: griffe.Object) -> int | None:
    """Itens que o griffe distribui pelos elementos da ``tuple`` devolvida; ``None`` se variádica."""
    retorno = objeto.returns if objeto.is_function else None
    # ``tuple[int]`` tem um elemento só, sem ``elements``; o griffe não o distribui.
    elementos = getattr(retorno, "is_tuple", False) and getattr(getattr(retorno, "slice", None), "elements", None)
    if not elementos:
        return 1
    return None if "..." in map(str, elementos) else len(elementos)


def _motivo_dos_retornos(objeto: griffe.Object, retornos: list[griffe.DocstringReturn]) -> str | None:
    esperados = _itens_esperados(objeto)
    if len(retornos) > 1 and esperados is not None and len(retornos) != esperados:
        return (
            f"Returns com {len(retornos)} itens para {esperados} valor(es) devolvido(s);"
            " recuar as linhas de continuação ou juntar a descrição numa entrada"
        )
    for retorno in retornos:
        # ``str: ...`` vira nome do valor; ``pd.DataFrame: ...``, começo da descrição.
        prefixo = _PREFIXO_DE_TIPO.match(retorno.description)
        tipo = retorno.name or (prefixo and prefixo.group(1))
        if tipo:
            return (
                f"Returns começa por '{tipo}:', que a referência mostra como nome ou na descrição;"
                " tirar o tipo quando a assinatura o anota, ou pô-lo entre parênteses"
            )
    if any(not retorno.annotation for retorno in retornos):
        return "Returns sem tipo; anotar o retorno da função ou, sem anotação, pôr o tipo entre parênteses"
    assinatura = objeto.returns if objeto.is_function else None
    if len(retornos) == 1 and assinatura is not None and str(retornos[0].annotation) != str(assinatura):
        return (
            f"Returns com '({retornos[0].annotation}):' em função anotada com '{assinatura}';"
            " tirar os parênteses, que sobrepõem a anotação"
        )
    return None


def problemas_do_codigo(codigo: str, modulo: str = "modulo", caminho: Path | None = None) -> list[str]:
    """Lista os problemas das docstrings de ``codigo``, um texto por problema."""
    caminho = caminho or Path(f"{modulo}.py")
    raiz = griffe.visit(modulo, filepath=caminho, code=codigo)
    problemas = []
    coletor = _Coletor()
    logger = logging.getLogger("griffe")
    nivel = logger.level
    logger.addHandler(coletor)
    logger.setLevel(logging.WARNING)
    try:
        for objeto in _objetos(raiz):
            if objeto.docstring is None:
                continue
            motivo = _motivo_do_estilo_numpy(objeto.docstring.value)
            if motivo:
                problemas.append(f"{caminho}:{objeto.docstring.lineno}: {objeto.name}: {motivo}")
            for secao in objeto.docstring.parse("google"):
                motivo = _motivo_da_secao(objeto, secao)
                if motivo:
                    problemas.append(f"{caminho}:{objeto.docstring.lineno}: {objeto.name}: {motivo}")
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel)
    problemas.extend(mensagem for mensagem in coletor.mensagens if _FALHA_DE_PAR in mensagem)
    return problemas


def _problemas_do_pacote() -> list[str]:
    raiz_src = RAIZ_PACOTE.parent
    problemas = []
    for arquivo in sorted(RAIZ_PACOTE.rglob("*.py")):
        modulo = ".".join(arquivo.relative_to(raiz_src).with_suffix("").parts)
        caminho = arquivo.relative_to(RAIZ_PACOTE.parents[1])
        problemas.extend(problemas_do_codigo(arquivo.read_text(encoding="utf-8"), modulo, caminho))
    return problemas


def test_docstrings_do_pacote_sao_lidas_como_pretendido():
    assert _problemas_do_pacote() == []


@pytest.mark.parametrize(
    "codigo",
    [
        'def f() -> int:\n'
        '    """Resumo.\n\n'
        '    Raises:\n'
        '        ValueError, TypeError,\n'
        '            KeyError: Quando falha.\n'
        '    """\n',
        'def f(a=None, b=None, c=None):\n'
        '    """Resumo.\n\n'
        '    Args:\n'
        '        a, b,\n'
        '        c (str | None): Datas.\n'
        '    """\n',
        'def f() -> "pd.DataFrame":\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        pd.DataFrame: Uma linha por processo, com\n'
        '        as colunas do schema.\n'
        '    """\n',
        'class A:\n'
        '    def f(self):\n'
        '        """Resumo.\n\n'
        '        Returns:\n'
        '            DataFrame com uma linha por processo.\n'
        '            Vazio quando nada casa.\n'
        '        """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Warns:\n'
        '        UserWarning: Quando a busca volta vazia.\n'
        '    """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Raises:\n'
        '        ValueError, TypeError: Quando falha.\n'
        '    """\n',
        'def f() -> "pd.DataFrame":\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        pd.DataFrame: Uma linha por processo.\n'
        '    """\n',
        'def f() -> str:\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        str: Caminho do diretório.\n'
        '    """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        dict[str, str]: Motivo de cada falha.\n'
        '    """\n',
        'def f() -> tuple[int, str]:\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        Primeiro.\n'
        '        Segundo, com\n'
        '        continuação sem recuo.\n'
        '    """\n',
        'def f() -> tuple[int, str]:\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        int: Primeiro.\n'
        '        str: Segundo.\n'
        '    """\n',
        'def f() -> "pd.DataFrame":\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        DataFrame: Uma linha por processo.\n'
        '    """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        str: Caminho do diretório.\n'
        '    """\n',
        'def f() -> "pd.DataFrame":\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        (pd.DataFrame | int): Uma linha por processo.\n'
        '    """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Returns:\n'
        '        DataFrame com uma linha por processo.\n'
        '    """\n',
        'def f(a: int | None = None):\n'
        '    """Resumo.\n\n'
        '    Args:\n'
        '        a (int | None): Número.\n'
        '    """\n',
        'class A:\n'
        '    """Resumo.\n\n'
        '    Args:\n'
        '        a (str): Texto.\n'
        '    """\n\n'
        '    def __init__(self, a: str):\n'
        '        self.a = a\n',
        'def f(a: int, b: int):\n'
        '    """Resumo.\n\n'
        '    Args:\n'
        '        a, b: Limites.\n'
        '    """\n',
        'def f(**kwargs: int):\n'
        '    """Resumo.\n\n'
        '    Args:\n'
        '        **kwargs (int): Filtros.\n'
        '    """\n',
        'def f(a: int):\n'
        '    """Resumo.\n\n'
        '    Parameters\n'
        '    ----------\n'
        '    a : int\n'
        '        Número.\n'
        '    """\n',
        'def f() -> int:\n'
        '    """Resumo.\n\n'
        '    Returns\n'
        '    -------\n'
        '    int\n'
        '        Número.\n'
        '    """\n',
        '"""Módulo.\n\n'
        'Notes\n'
        '-----\n'
        'Texto.\n'
        '"""\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    Aliases deprecados (popados antes do pydantic):\n'
        '        * ``query`` -> ``pesquisa``\n'
        '    """\n',
        'def f():\n'
        '    """Resumo.\n\n'
        '    A implementação fica em:\n'
        '    - ``juscraper.courts``\n'
        '    """\n',
    ],
    ids=[
        "raises-com-virgula",
        "args-partido",
        "returns-sem-recuo",
        "returns-sem-anotacao",
        "warns",
        "raises-numa-linha",
        "returns-prefixo-com-ponto",
        "returns-tipo-lido-como-nome",
        "returns-prefixo-sem-anotacao",
        "tupla-com-itens-a-mais",
        "tupla-com-prefixo",
        "returns-nome-curto-do-tipo",
        "returns-nome-sem-anotacao",
        "returns-parenteses-com-anotacao",
        "returns-sem-tipo",
        "args-tipo-com-anotacao",
        "args-tipo-com-anotacao-na-classe",
        "args-anotados-agrupados",
        "kwargs-tipo-com-anotacao",
        "numpy-parameters",
        "numpy-returns",
        "numpy-no-modulo",
        "lista-sob-titulo-nao-reconhecido",
        "lista-colada-ao-paragrafo",
    ],
)
def test_forma_lida_errado_e_reprovada(codigo):
    assert problemas_do_codigo(codigo)


def test_forma_correta_e_tupla_passam():
    codigo = (
        "def f(a=None, b=None) -> int:\n"
        '    """Resumo.\n\n'
        "    Args:\n"
        "        a, b (str | None): Datas.\n\n"
        "    Raises:\n"
        "        ValueError: Quando falha.\n"
        "        TypeError: Quando falha.\n\n"
        "    Returns:\n"
        "        Uma descrição: com dois-pontos\n"
        "            em duas linhas.\n"
        '    """\n\n'
        "def g() -> tuple[int, str]:\n"
        '    """Resumo.\n\n'
        "    Returns:\n"
        "        Primeiro.\n"
        "        Segundo, com\n"
        "            continuação recuada.\n"
        '    """\n\n'
        "def h() -> tuple[int, str]:\n"
        '    """Resumo.\n\n'
        "    Returns:\n"
        "        ``(numero, texto)`` numa entrada só.\n"
        '    """\n\n'
        "def i() -> tuple[int, ...]:\n"
        '    """Resumo.\n\n'
        "    Returns:\n"
        "        Primeiro.\n"
        "        Segundo.\n"
        "        Terceiro.\n"
        '    """\n\n'
        "def j():\n"
        '    """Resumo.\n\n'
        "    Returns:\n"
        "        (dict[str, str]): Motivo de cada falha.\n"
        '    """\n\n'
        "def lista():\n"
        '    """Resumo, com lista depois de linha em branco:\n\n'
        "    * um item\n"
        "      com continuação\n"
        "    * outro item\n\n"
        "    Aliases deprecados:\n"
        "        * ``query`` -> ``pesquisa``\n"
        '    """\n\n'
        "def k() -> tuple[int]:\n"
        '    """Resumo.\n\n'
        "    Returns:\n"
        "        Único elemento.\n"
        '    """\n\n'
        "def m(a: int, b=None, **kwargs):\n"
        '    """Resumo.\n\n'
        "    Args:\n"
        "        a: Número, tipo vindo da anotação.\n"
        "        b (str | None): Texto, sem anotação.\n"
        "        **kwargs: Filtros:\n\n"
        "            * ``c`` (int): Filtro.\n"
        '    """\n'
    )
    assert problemas_do_codigo(codigo) == []


def test_griffe_parte_retorno_e_perde_excecoes():
    """Amarra a premissa do teste ao parser real que o quartodoc usa."""
    secoes = griffe.Docstring("Resumo.\n\nReturns:\n    int: Uma\n    descrição.\n", parser="google").parsed
    retornos = next(s for s in secoes if isinstance(s, griffe.DocstringSectionReturns))
    assert len(retornos.value) == 2
    # Continuação no recuo do item: sobra só a exceção da última linha.
    secoes = griffe.Docstring(
        "Resumo.\n\nRaises:\n    ValueError, TypeError,\n    KeyError: Quando falha.\n", parser="google"
    ).parsed
    excecoes = next(s for s in secoes if isinstance(s, griffe.DocstringSectionRaises))
    assert [str(e.annotation) for e in excecoes.value] == ["KeyError"]
    # Continuação recuada: a seção some da referência.
    secoes = griffe.Docstring(
        "Resumo.\n\nRaises:\n    ValueError, TypeError,\n        KeyError: Quando falha.\n", parser="google"
    ).parsed
    assert not any(isinstance(s, griffe.DocstringSectionRaises) for s in secoes)


def test_griffe_poe_a_anotacao_na_entrada_sem_tipo():
    """Amarra a premissa da regra de Args: sem tipo escrito, a entrada recebe o objeto da anotação."""
    raiz = griffe.visit("m", filepath=Path("m.py"), code=(
        "def f(a: int, b: str):\n"
        '    """Resumo.\n\n'
        "    Args:\n"
        "        a: Número.\n"
        "        b (str): Texto.\n"
        '    """\n'
    ))
    funcao = raiz["f"]
    secao = next(s for s in funcao.docstring.parse("google") if isinstance(s, griffe.DocstringSectionParameters))
    a, b = secao.value
    assert a.annotation is funcao.parameters["a"].annotation
    assert b.annotation is not funcao.parameters["b"].annotation
