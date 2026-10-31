"""Gera, a partir do código, as tabelas de cobertura do README e da documentação.

Uso, na raiz do repositório::

    uv run python scripts/tabela_cobertura.py           # reescreve os arquivos
    uv run python scripts/tabela_cobertura.py --check   # só confere; sai com 1 se divergir

A fonte dos raspadores é ``juscraper._SCRAPERS``, o mesmo registro que
``jus.scraper()`` consulta. Cada classe é inspecionada depois de resolvida a
herança (``_esaj``, ``_trf`` e mixins), e um método entra na tabela quando é
público, é um endpoint de consulta e não é stub. Stub é o método cujo corpo,
tirada a docstring, é só ``raise NotImplementedError(...)``: os tribunais o
mantêm para a assinatura uniforme, mas ele não faz consulta nenhuma.

As tabelas ficam entre os marcadores ``INICIO`` e ``FIM`` de cada arquivo em
``ARQUIVOS``. O texto em volta, como a nota sobre o CAPTCHA do TJAP, continua
editado à mão. ``tests/test_tabela_cobertura.py`` roda o modo ``--check``.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import sys
import textwrap
from pathlib import Path

import juscraper

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVOS = (RAIZ / "README.md", RAIZ / "docs" / "index.qmd")
INICIO = "<!-- tabela-cobertura:inicio (gerada por scripts/tabela_cobertura.py; não editar à mão) -->"
FIM = "<!-- tabela-cobertura:fim -->"

# Os quatro endpoints dos tribunais saem nesta ordem; os demais, em ordem alfabética depois deles.
ORDEM_CANONICA = ("cpopg", "cposg", "cjsg", "cjpg")

# Métodos públicos que não são consulta: configuração, autenticação e as
# listas de valores aceitos nos filtros da família eSAJ.
AUXILIARES = frozenset(
    {
        "auth",
        "auth_firefox",
        "auth_govbr",
        "set_download_path",
        "set_method",
        "set_verbose",
        "listar_assuntos",
        "listar_classes",
        "listar_orgaos",
        "listar_varas",
    }
)
# ``*_download`` e ``*_parse`` são as etapas separadas de um endpoint que já aparece na linha.
SUFIXOS_DE_ETAPA = ("_download", "_parse")

# O registro que ``jus.scraper()`` consulta: um raspador fora dele não é público.
REGISTRO: dict[str, str] = juscraper._SCRAPERS  # noqa: SLF001  # pylint: disable=protected-access

# Marca ao lado do método, explicada em nota fora do bloco gerado.
MARCAS = {("tjap", "cjsg"): "⚠️"}

# Nome exibido dos agregadores; os tribunais usam a sigla em maiúsculas.
NOMES_AGREGADORES = {
    "comunica_cnj": "ComunicaCNJ",
    "datajud": "Datajud",
    "falcao": "Falcao",
    "jusbr": "JusBR",
    "pdpj": "PDPJ",
}


def classe_do_raspador(sigla: str) -> type:
    """Importa a classe registrada para ``sigla`` em ``REGISTRO``."""
    modulo, nome = REGISTRO[sigla].split(":")
    classe: type = getattr(importlib.import_module(modulo), nome)
    return classe


def e_stub(metodo: object) -> bool:
    """Diz se o corpo do método, sem a docstring, é só ``raise NotImplementedError``.

    A leitura é pela árvore sintática, e não pela busca do texto no código,
    porque um método implementado pode levantar ``NotImplementedError`` num
    ramo de validação e continuaria fora da tabela.
    """
    funcao = inspect.unwrap(metodo)  # type: ignore[arg-type]
    try:
        fonte = textwrap.dedent(inspect.getsource(funcao))
    except (OSError, TypeError):
        return False
    definicao = ast.parse(fonte).body[0]
    if not isinstance(definicao, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    corpo = definicao.body
    if corpo and isinstance(corpo[0], ast.Expr) and isinstance(corpo[0].value, ast.Constant):
        corpo = corpo[1:]
    if len(corpo) != 1 or not isinstance(corpo[0], ast.Raise) or corpo[0].exc is None:
        return False
    excecao = corpo[0].exc
    if isinstance(excecao, ast.Call):
        excecao = excecao.func
    return isinstance(excecao, ast.Name) and excecao.id == "NotImplementedError"


def endpoints(classe: type) -> list[str]:
    """Lista os endpoints implementados da classe, na ordem de exibição."""
    nomes = []
    for nome in dir(classe):
        if nome.startswith("_") or not nome.islower() or nome in AUXILIARES or nome.endswith(SUFIXOS_DE_ETAPA):
            continue
        estatico = inspect.getattr_static(classe, nome)
        if isinstance(estatico, property) or not callable(getattr(classe, nome)):
            continue
        if not e_stub(getattr(classe, nome)):
            nomes.append(nome)
    return sorted(
        nomes,
        key=lambda nome: (
            ORDEM_CANONICA.index(nome) if nome in ORDEM_CANONICA else len(ORDEM_CANONICA),
            nome,
        ),
    )


def cobertura() -> dict[str, dict[str, list[str]]]:
    """Agrupa ``{sigla: endpoints}`` em ``tribunais`` e ``agregadores``, pelo pacote da classe."""
    grupos: dict[str, dict[str, list[str]]] = {"tribunais": {}, "agregadores": {}}
    for sigla in REGISTRO:
        classe = classe_do_raspador(sigla)
        grupo = "agregadores" if classe.__module__.startswith("juscraper.aggregators.") else "tribunais"
        grupos[grupo][sigla] = endpoints(classe)
    return grupos


def _chave_tribunal(sigla: str) -> tuple[int, str]:
    # STF, depois os TJs e por fim os TRFs; sigla de outro ramo vai para o fim.
    for posicao, prefixo in enumerate(("stf", "tj", "trf")):
        if sigla.startswith(prefixo):
            return (posicao, sigla)
    return (3, sigla)


def _tabela(cabecalho: tuple[str, str], linhas: list[tuple[str, str]]) -> list[str]:
    largura = max(len(cabecalho[0]), *(len(nome) for nome, _ in linhas))
    saida = [
        f"| {cabecalho[0]:<{largura}} | {cabecalho[1]} |",
        f"|{'-' * (largura + 2)}|{'-' * (len(cabecalho[1]) + 2)}|",
    ]
    saida += [f"| {nome:<{largura}} | {metodos} |" for nome, metodos in linhas]
    return saida


def _celula(sigla: str, metodos: list[str]) -> str:
    return ", ".join(f"{metodo} {MARCAS[sigla, metodo]}" if (sigla, metodo) in MARCAS else metodo for metodo in metodos)


def bloco() -> str:
    """Monta o bloco Markdown com as duas tabelas, entre os marcadores."""
    grupos = cobertura()
    tribunais = [
        (sigla.upper(), _celula(sigla, metodos))
        for sigla, metodos in sorted(grupos["tribunais"].items(), key=lambda item: _chave_tribunal(item[0]))
    ]
    agregadores = [
        (NOMES_AGREGADORES.get(sigla, sigla), _celula(sigla, metodos))
        for sigla, metodos in sorted(grupos["agregadores"].items())
    ]
    linhas = [
        INICIO,
        "",
        "### Tribunais Disponíveis",
        "",
        *_tabela(("Tribunal", "Funcionalidades Disponíveis"), tribunais),
        "",
        "### Agregadores Disponíveis",
        "",
        *_tabela(("Nome", "Funcionalidades Disponíveis"), agregadores),
        "",
        FIM,
    ]
    return "\n".join(linhas)


def substituir(texto: str, novo_bloco: str, caminho: Path) -> str:
    """Troca o trecho entre ``INICIO`` e ``FIM`` (inclusive) por ``novo_bloco``."""
    if texto.count(INICIO) != 1 or texto.count(FIM) != 1:
        raise SystemExit(f"{caminho}: os marcadores da tabela de cobertura devem aparecer uma vez cada.")
    antes, resto = texto.split(INICIO)
    _, depois = resto.split(FIM)
    return antes + novo_bloco + depois


def main(argumentos: list[str] | None = None) -> int:
    """Reescreve as tabelas, ou só confere com ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="não grava; sai com 1 se algum arquivo divergir")
    opcoes = parser.parse_args(argumentos)
    novo_bloco = bloco()
    divergentes = []
    for caminho in ARQUIVOS:
        texto = caminho.read_text(encoding="utf-8")
        atualizado = substituir(texto, novo_bloco, caminho)
        if atualizado == texto:
            continue
        divergentes.append(caminho.relative_to(RAIZ))
        if not opcoes.check:
            caminho.write_text(atualizado, encoding="utf-8")
    if opcoes.check and divergentes:
        sys.stderr.write(
            "Tabela de cobertura desatualizada em: "
            + ", ".join(map(str, divergentes))
            + ". Rode `uv run python scripts/tabela_cobertura.py`.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
