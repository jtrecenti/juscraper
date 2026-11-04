"""Reprova seção de docstring com o nome em português, como ``Argumentos:``.

O quartodoc usa o parser Google do griffe, que reconhece a seção pelo nome em
inglês (``Args``, ``Returns``, ``Raises``, ``Examples``, ``Attributes``). Com
o nome traduzido, o griffe lê o bloco como admonition de texto livre: a
referência perde a tabela de parâmetros, o tipo de retorno e a lista de
exceções, e nada avisa no build. O texto dentro da seção continua em
português; só o nome da seção fica em inglês.

``Avisos:`` e ``Aliases deprecados:`` ficam fora da lista de propósito: são
texto livre por convenção do CONTRIBUTING, porque o quartodoc não renderiza a
seção ``Warns`` e não há seção Google para aliases.
"""

import ast
import unicodedata
from pathlib import Path

import griffe
import pytest

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"
_NOS_COM_DOCSTRING = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)

# Nome em português, sem acento e em minúsculas, -> cabeçalho que o griffe reconhece.
SECOES_TRADUZIDAS = {
    "argumentos": "Args:",
    "argumento": "Args:",
    "parametros": "Args:",
    "parametro": "Args:",
    "retorno": "Returns:",
    "retornos": "Returns:",
    "retorna": "Returns:",
    "excecoes": "Raises:",
    "excecao": "Raises:",
    "levanta": "Raises:",
    "exemplos": "Examples: Exemplo",
    "exemplo": "Examples: Exemplo",
    "atributos": "Attributes:",
}


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def _recuo(linha: str) -> int:
    return len(linha) - len(linha.lstrip())


def problemas_da_docstring(texto: str) -> list[tuple[int, str]]:
    """Lista ``(deslocamento, motivo)`` para cada cabeçalho traduzido.

    Conta como cabeçalho a linha ``Nome:``, com o dois-pontos colado ao nome,
    sozinha ou seguida de título quando a linha seguinte é mais recuada, que é
    a forma de seção do parser Google. A frase ``Retorna: o DataFrame.`` no
    meio de um parágrafo e o resumo ``Levanta :class:`Erro` quando...`` não
    contam.
    """
    linhas = texto.expandtabs().splitlines()
    # Tira a margem comum para o recuo da primeira linha, colada às aspas,
    # ser comparável ao das outras.
    margem = min((_recuo(linha) for linha in linhas[1:] if linha.strip()), default=0)
    linhas = [linha.strip() if i == 0 else linha[margem:] for i, linha in enumerate(linhas)]
    problemas = []
    for i, linha in enumerate(linhas):
        nome, dois_pontos, resto = linha.strip().partition(":")
        if not dois_pontos or nome != nome.rstrip() or _normalizar(nome) not in SECOES_TRADUZIDAS:
            continue
        seguinte = next((proxima for proxima in linhas[i + 1 :] if proxima.strip()), "")
        if resto.strip() and _recuo(seguinte) <= _recuo(linha):
            continue
        problemas.append((i, f"seção {nome.strip()!r}: usar {SECOES_TRADUZIDAS[_normalizar(nome)]!r}"))
    return problemas


def _violacoes_do_pacote() -> list[str]:
    violacoes = []
    for arquivo in sorted(RAIZ_PACOTE.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        for no in ast.walk(arvore):
            if not isinstance(no, _NOS_COM_DOCSTRING) or not no.body:
                continue
            primeiro = no.body[0]
            if not (
                isinstance(primeiro, ast.Expr)
                and isinstance(primeiro.value, ast.Constant)
                and isinstance(primeiro.value.value, str)
            ):
                continue
            caminho = arquivo.relative_to(RAIZ_PACOTE.parents[1])
            for deslocamento, motivo in problemas_da_docstring(primeiro.value.value):
                violacoes.append(f"{caminho}:{primeiro.value.lineno + deslocamento}: {motivo}")
    return violacoes


def test_secoes_do_pacote_tem_nome_em_ingles():
    assert _violacoes_do_pacote() == []


@pytest.mark.parametrize(
    "docstring",
    [
        "Resumo.\n\n    Argumentos:\n        x: Valor.\n    ",
        "Resumo.\n\n    Parâmetros:\n        x: Valor.\n    ",
        "Resumo.\n\n    Retorno:\n        pd.DataFrame: Resultado.\n    ",
        "Resumo.\n\n    Retorna:\n        pd.DataFrame: Resultado.\n    ",
        "Resumo.\n\n    Exceções:\n        TypeError: Quando falta x.\n    ",
        "Resumo.\n\n    Exemplos:\n        Chamar com x=1.\n    ",
        "Resumo.\n\n    Atributos:\n        x: Valor.\n    ",
        "Resumo.\n\n    RETORNO:\n        pd.DataFrame: Resultado.\n    ",
        "Resumo.\n\n    Exemplos: uso básico\n        Chamar com x=1.\n    ",
        "Resumo.\n\n    Argumentos:\n\n        x: Valor.\n    ",
    ],
    ids=[
        "argumentos",
        "parametros-com-acento",
        "retorno",
        "retorna",
        "excecoes-com-acento",
        "exemplos",
        "atributos",
        "maiusculas",
        "exemplos-com-titulo",
        "linha-em-branco-abaixo",
    ],
)
def test_cabecalho_traduzido_e_reprovado(docstring):
    assert problemas_da_docstring(docstring)


def test_secoes_em_ingles_texto_livre_e_frase_com_dois_pontos_passam():
    docstring = (
        "Resumo.\n\n"
        "    Retorna: o DataFrame com uma linha por processo.\n"
        "    A frase acima é texto, não seção.\n\n"
        "    Args:\n"
        "        x: Valor.\n\n"
        "    Returns:\n"
        "        pd.DataFrame: Resultado.\n\n"
        "    Raises:\n"
        "        TypeError: Quando falta x.\n\n"
        "    Avisos:\n"
        "        ``UserWarning``: Quando uma página falha.\n\n"
        "    Aliases deprecados:\n"
        "        * ``query`` -> ``pesquisa``.\n\n"
        "    Examples: Exemplo\n"
        "        >>> f(x=1)\n    "
    )
    assert problemas_da_docstring(docstring) == []


def test_resumo_que_comeca_com_verbo_e_papel_sphinx_passa():
    docstring = "Levanta :class:`BotChallengeBlockedError` no 403.\n\n    Só esse formato.\n    "
    assert problemas_da_docstring(docstring) == []


def test_griffe_le_secao_traduzida_como_texto_livre():
    """Amarra a premissa do teste ao parser real que o quartodoc usa."""
    secoes = griffe.Docstring("Resumo.\n\nArgumentos:\n    x: Valor.\n", parser="google").parsed
    assert not any(isinstance(secao, griffe.DocstringSectionParameters) for secao in secoes)
    secoes = griffe.Docstring("Resumo.\n\nArgs:\n    x: Valor.\n", parser="google").parsed
    assert any(isinstance(secao, griffe.DocstringSectionParameters) for secao in secoes)
