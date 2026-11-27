"""O aviso de busca vazia dos tribunais só é procurado por ``AvisoVazio``.

Ementas e sentenças citam as frases do aviso ("nenhum documento encontrado
nos autos"). Um check que procura a frase no HTML inteiro lê a página de
resultados como busca vazia, e o download para na primeira página sem aviso
(CONTRIBUTING > Contagem de páginas e resultados em HTML). ``AvisoVazio``
restringe a frase ao contêiner do aviso; :meth:`AvisoVazio.presente` faz a
checagem fora da contagem.

O gate procura em ``src/juscraper/courts/`` as frases de busca vazia em
literais de string ou bytes fora de ``AvisoVazio(...)``, e o acesso a ``.marcadores``,
que levaria a frase para um check feito à mão. Não contam docstrings, nem as
mensagens de ``raise``, ``avisar`` e dos métodos de ``logger``,
``logging`` e ``warnings``.
"""

import ast
import re

import pytest

from tests.test_docstring_examples import _NOS_COM_DOCSTRING, RAIZ_PACOTE

RAIZ_TRIBUNAIS = RAIZ_PACOTE / "courts"

_FRASE_DE_BUSCA_VAZIA = re.compile(
    r"nenhuma?\s+\w+\s+(foi\s+)?encontrad"
    r"|n[aã]o\s+foram\s+encontrad"
    r"|n[aã]o\s+h[aá]\s+resultados"
    r"|sem\s+resultados?\s+para",
    re.IGNORECASE,
)
# Mensagens: ``avisar(...)`` e os métodos de ``logger``, ``logging`` e ``warnings``.
_MODULOS_DE_MENSAGEM = frozenset({"logger", "logging", "warnings"})

# Caminho relativo a ``src/juscraper/courts`` -> motivo. Cada entrada precisa
# continuar com achado; a que fica sem sai da lista.
EXCECOES = {
    "tjap/download.py": "compara a mensagem do envelope JSON da API, não HTML",
    "tjmg/cposg_parse.py": (
        "consulta por número de processo; a página não traz ementas que citem a frase"
    ),
    "_esaj/parse.py": (
        "_has_zero_results procura os marcadores no texto da página inteira; "
        "pendente de AvisoVazio com sample de cada tribunal eSAJ"
    ),
    "trf3/cjsg_download.py": (
        "_check_lista procura o aviso no texto da página inteira; "
        "pendente em outra sessão (AvisoVazio.presente)"
    ),
}


def _e_aviso_vazio_ou_mensagem(no: ast.Call) -> bool:
    funcao = no.func
    if isinstance(funcao, ast.Name):
        return funcao.id in {"AvisoVazio", "avisar"}
    return (
        isinstance(funcao, ast.Attribute)
        and isinstance(funcao.value, ast.Name)
        and funcao.value.id in _MODULOS_DE_MENSAGEM
    )


def _texto(no: ast.AST) -> str | None:
    if isinstance(no, ast.Constant) and isinstance(no.value, (str, bytes)):
        return no.value if isinstance(no.value, str) else no.value.decode("utf-8", "replace")
    return None


def _docstrings(arvore: ast.Module) -> set[int]:
    ids: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, _NOS_COM_DOCSTRING):
            primeiro = no.body[0] if no.body else None
            if isinstance(primeiro, ast.Expr) and isinstance(primeiro.value, ast.Constant):
                ids.add(id(primeiro.value))
    return ids


def checks_fora_do_aviso(codigo: str) -> list[tuple[int, str]]:
    """Lista ``(linha, trecho)`` de cada frase de busca vazia fora de ``AvisoVazio``."""
    arvore = ast.parse(codigo)
    docstrings = _docstrings(arvore)
    achados: list[tuple[int, str]] = []

    def visitar(no: ast.AST) -> None:
        for filho in ast.iter_child_nodes(no):
            if isinstance(filho, ast.Raise):
                continue
            if isinstance(filho, ast.Call) and _e_aviso_vazio_ou_mensagem(filho):
                continue
            if isinstance(filho, ast.Attribute) and filho.attr == "marcadores":
                achados.append((filho.lineno, ".marcadores"))
            texto = _texto(filho)
            if (
                texto is not None
                and id(filho) not in docstrings
                and (frase := _FRASE_DE_BUSCA_VAZIA.search(texto))
            ):
                achados.append((filho.lineno, frase.group(0)))
            visitar(filho)

    visitar(arvore)
    return achados


def _achados_dos_tribunais() -> dict[str, list[tuple[int, str]]]:
    achados: dict[str, list[tuple[int, str]]] = {}
    for arquivo in sorted(RAIZ_TRIBUNAIS.rglob("*.py")):
        if encontrados := checks_fora_do_aviso(arquivo.read_text(encoding="utf-8")):
            achados[arquivo.relative_to(RAIZ_TRIBUNAIS).as_posix()] = encontrados
    return achados


def test_aviso_de_busca_vazia_so_dentro_de_aviso_vazio():
    violacoes = {caminho: v for caminho, v in _achados_dos_tribunais().items() if caminho not in EXCECOES}
    assert not violacoes, (
        "Frase de busca vazia fora de AvisoVazio(...): ponha o contêiner do aviso e as "
        "frases em AvisoVazio(seletores, marcadores) e cheque com .presente(html) ou "
        f"com aviso_vazio= no extract_count_with_cascade. Achados: {violacoes}"
    )


def test_excecoes_ainda_tem_achado():
    achados = _achados_dos_tribunais()
    sem_achado = sorted(caminho for caminho in EXCECOES if caminho not in achados)
    assert not sem_achado, f"Exceções sem achado; retire de EXCECOES: {sem_achado}"


@pytest.mark.parametrize(
    ("codigo", "esperado"),
    [
        ('_M = ("nenhum documento encontrado",)\n', [(1, "nenhum documento encontrad")]),
        ('ok = "Nenhum Resultado Encontrado" in html\n', [(1, "Nenhum Resultado Encontrad")]),
        ('ok = b"Nenhum documento encontrado" in resp.content\n', [(1, "Nenhum documento encontrad")]),
        ('ok = "nenhuma jurisprudência encontrada" in texto\n', [(1, "nenhuma jurisprudência encontrad")]),
        ('ok = "Não há resultados" in texto\n', [(1, "Não há resultados")]),
        ('ok = resultado.info("Nenhum documento encontrado")\n', [(1, "Nenhum documento encontrad")]),
        ('ok = any(m in t for m in _AVISO.marcadores)\n', [(1, ".marcadores")]),
        ('msg = "nenhum documento de acórdão acessível"\n', []),
        ('_A = AvisoVazio(("td",), ("Nenhum documento encontrado",))\n', []),
        ('def f():\n    """Nenhum documento encontrado."""\n', []),
        ('raise ValueError(f"nenhum documento encontrado em {url}")\n', []),
        ('avisar("O portal respondeu Nenhum documento encontrado")\n', []),
        ('logger.info("Nenhum resultado encontrado para a busca.")\n', []),
    ],
)
def test_checks_fora_do_aviso(codigo, esperado):
    assert checks_fora_do_aviso(codigo) == esperado
