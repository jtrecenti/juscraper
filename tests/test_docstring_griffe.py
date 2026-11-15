"""Reprova docstrings que o parser Google do griffe lê diferente do pretendido.

O quartodoc usa esse parser, e o ``quartodoc build`` passa mesmo quando ele lê
errado; o defeito só aparece na referência publicada. O teste reprova aviso de
falha do par ``nome: descrição`` (lista de exceções ou de nomes partida em duas
linhas), entrada de ``Raises:`` com várias exceções, ``Returns:`` com um número
de itens que não é um nem o de elementos da ``tuple`` devolvida (continuação
sem recuo), ``Returns:`` que começa pelo tipo seguido de dois-pontos e a seção
``Warns:``, que derruba o build. As formas certas estão no CONTRIBUTING, em
"Docstrings de métodos públicos com kwargs".

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
_PREFIXO_DE_TIPO = re.compile(r"^([A-Za-z_][\w.]*(\[[^:]*\])?(\s*\|\s*[A-Za-z_][\w.]*(\[[^:]*\])?)*):(\s|$)")


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


def _motivo_da_secao(objeto: griffe.Object, secao: griffe.DocstringSection) -> str | None:
    if isinstance(secao, griffe.DocstringSectionWarns):
        return "seção 'Warns:', que derruba o quartodoc build; usar 'Avisos:'"
    if isinstance(secao, griffe.DocstringSectionRaises):
        grupos = [str(excecao.annotation) for excecao in secao.value if "," in str(excecao.annotation)]
        if grupos:
            return f"Raises com várias exceções numa entrada ({'; '.join(grupos)}); usar uma por entrada"
    if isinstance(secao, griffe.DocstringSectionReturns):
        return _motivo_dos_retornos(objeto, secao.value)
    return None


def _itens_esperados(objeto: griffe.Object) -> int | None:
    """Itens que o griffe distribui pelos elementos da ``tuple`` devolvida; ``None`` se variádica."""
    retorno = objeto.returns if objeto.is_function else None
    if not getattr(retorno, "is_tuple", False):
        return 1
    elementos = retorno.slice.elements
    return None if "..." in map(str, elementos) else len(elementos)


def _motivo_dos_retornos(objeto: griffe.Object, retornos: list[griffe.DocstringReturn]) -> str | None:
    esperados = _itens_esperados(objeto)
    if len(retornos) > 1 and esperados is not None and len(retornos) != esperados:
        return (
            f"Returns com {len(retornos)} itens para {esperados} valor(es) devolvido(s);"
            " recuar as linhas de continuação"
        )
    for retorno in retornos:
        if retorno.name and retorno.name == str(retorno.annotation):
            tipo = retorno.name
        elif prefixo := _PREFIXO_DE_TIPO.match(retorno.description):
            tipo = prefixo.group(1)
        else:
            continue
        return (
            f"Returns começa pelo tipo ('{tipo}:'), que a referência repete;"
            " tirar o tipo quando a assinatura o anota, ou pô-lo entre parênteses"
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
