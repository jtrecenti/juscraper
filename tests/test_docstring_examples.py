"""Exige que exemplos ``>>>`` das docstrings fiquem na seção ``Examples: Exemplo``.

O quartodoc usa o parser Google do griffe. Só a palavra-chave ``Examples``
produz ``DocstringSectionExamples``, que o renderer publica como bloco
``python``; o texto depois dos dois-pontos vira o título da seção, por isso
``Examples: Exemplo`` sai com cabeçalho em português. Com ``Exemplo:``, o
griffe cria uma admonition, o quartodoc repassa a descrição crua e o Pandoc lê
cada ``>>>`` como três citações aninhadas, colando o código num parágrafo. O
mesmo acontece com ``>>>`` em texto livre ou no cabeçalho NumPy
``Examples``/``--------``, que o parser Google não reconhece.
"""

import ast
from pathlib import Path

import pytest

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "juscraper"
CABECALHO = "Examples: Exemplo"
_NOS_COM_DOCSTRING = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _recuo(linha: str) -> int:
    return len(linha) - len(linha.lstrip())


def _linhas_sem_margem(texto: str) -> list[str]:
    """Remove a margem comum preservando a posição de cada linha.

    ``inspect.cleandoc`` descarta as linhas em branco iniciais, o que desloca
    o número de linha quando as aspas triplas de abertura ficam sozinhas. Aqui a
    linha ``i`` continua correspondendo à linha ``lineno + i`` do arquivo.
    """
    linhas = texto.expandtabs().splitlines()
    if not linhas:
        return []
    margem = min((_recuo(linha) for linha in linhas[1:] if linha.strip()), default=0)
    return [linhas[0].strip(), *(linha[margem:] for linha in linhas[1:])]


def problemas_da_docstring(texto: str) -> list[tuple[int, str]]:
    """Lista ``(deslocamento, motivo)`` para cada violação da convenção."""
    linhas = _linhas_sem_margem(texto)
    problemas = []
    for i, linha in enumerate(linhas):
        if linha.strip() == CABECALHO and (i + 1 == len(linhas) or not linhas[i + 1].strip()):
            # O griffe recusa a seção quando há linha em branco logo abaixo
            # do título, e o conteúdo volta a ser texto livre.
            problemas.append((i, f"linha em branco ou fim logo abaixo de {CABECALHO!r}"))
        if not linha.lstrip().startswith(">>>"):
            continue
        recuo = _recuo(linha)
        dono = next(
            (anterior for anterior in reversed(linhas[:i]) if anterior.strip() and _recuo(anterior) < recuo),
            None,
        )
        if dono != CABECALHO:
            problemas.append((i, f"'>>>' fora de {CABECALHO!r} (seção: {dono!r})"))
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
            for deslocamento, motivo in problemas_da_docstring(primeiro.value.value):
                caminho = arquivo.relative_to(RAIZ_PACOTE.parents[1])
                violacoes.append(f"{caminho}:{primeiro.value.lineno + deslocamento}: {motivo}")
    return violacoes


def test_exemplos_do_pacote_ficam_na_secao_examples():
    assert _violacoes_do_pacote() == []


@pytest.mark.parametrize(
    "docstring",
    [
        'Resumo.\n\n    Exemplo:\n        >>> import juscraper as jus\n    ',
        'Resumo.\n\n    Example:\n        >>> import juscraper as jus\n    ',
        'Resumo.\n\n    Examples\n    --------\n    >>> import juscraper as jus\n    ',
        'Resumo.\n\n    >>> import juscraper as jus\n    ',
        'Resumo.\n\n    Args:\n        x: Valor.\n\n            >>> x = 1\n    ',
        'Resumo.\n\n    Examples: Exemplo\n\n        >>> import juscraper as jus\n    ',
    ],
    ids=["exemplo-pt", "example-singular", "numpy", "texto-livre", "dentro-de-args", "linha-em-branco"],
)
def test_formas_que_quebram_a_referencia_sao_reprovadas(docstring):
    assert problemas_da_docstring(docstring)


def test_forma_canonica_passa_com_continuacao_saida_e_linha_em_branco():
    docstring = (
        "Resumo.\n\n"
        "    Examples: Exemplo\n"
        "        >>> dj.contar_processos(\n"
        '        ...     tribunal="TRF1",\n'
        "        ... )\n"
        "          tribunal  count\n\n"
        "        >>> # Segundo grupo\n"
        "        >>> n = 1\n\n"
        "    See also:\n"
        "        :meth:`listar_processos`.\n    "
    )
    assert problemas_da_docstring(docstring) == []


def test_griffe_le_a_forma_canonica_como_secao_de_exemplos_com_titulo_em_portugues():
    """Amarra a convenção ao parser real; roda onde o extra ``docs`` está instalado."""
    griffe = pytest.importorskip("griffe")
    secoes = griffe.Docstring(
        "Resumo.\n\nExamples: Exemplo\n    >>> import juscraper as jus\n", parser="google"
    ).parsed
    exemplos = [secao for secao in secoes if isinstance(secao, griffe.DocstringSectionExamples)]
    assert len(exemplos) == 1
    assert exemplos[0].title == "Exemplo"
    assert [tipo.value for tipo, _ in exemplos[0].value] == ["examples"]


def test_griffe_nao_deixa_exemplo_fora_de_secao_de_exemplos_no_pacote():
    """Confere no parser real o que o teste por ``ast`` aproxima.

    O griffe não carrega subpacotes sem ``__init__.py``, como
    ``juscraper.core``; esses ficam cobertos só pelo teste por ``ast``.
    """
    griffe = pytest.importorskip("griffe")
    pacote = griffe.load("juscraper", search_paths=[str(RAIZ_PACOTE.parent)], docstring_parser="google")
    violacoes = []
    pendentes = [pacote]
    while pendentes:
        objeto = pendentes.pop()
        pendentes.extend(membro for membro in objeto.members.values() if not membro.is_alias)
        if objeto.docstring is None:
            continue
        for secao in objeto.docstring.parsed:
            if isinstance(secao, griffe.DocstringSectionExamples):
                if secao.title != "Exemplo":
                    violacoes.append(f"{objeto.path}: título {secao.title!r}")
                continue
            texto = secao.value if isinstance(secao.value, str) else getattr(secao.value, "description", "")
            if any(linha.lstrip().startswith(">>>") for linha in str(texto).splitlines()):
                violacoes.append(f"{objeto.path}: '>>>' em {type(secao).__name__}")
    assert violacoes == []
