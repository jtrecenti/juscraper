r"""Tira dos notebooks de ``docs/notebooks/`` o ruído da execução, sem apagar os outputs.

Uso, na raiz do repositório::

    uv run python scripts/limpar_notebooks.py docs/notebooks/tjes.ipynb   # limpa no lugar
    uv run python scripts/limpar_notebooks.py                             # todos os notebooks de docs/notebooks/
    uv run python scripts/limpar_notebooks.py --check                     # só confere; sai com 1 se algum mudaria

Os outputs gravados são a documentação que o site Quarto mostra; o script só
remove o que muda a cada execução e não diz nada ao leitor:

- ``metadata.execution`` de cada célula, os carimbos de horário que
  ``jupyter nbconvert --execute`` grava (``iopub.execute_input`` e afins);
- os estados intermediários das barras do tqdm. Saídas ``stream`` seguidas e de
  mesmo nome viram uma só, e em cada linha fica só o texto depois do último
  ``\r``, que é o que o terminal mostraria: a linha final de cada barra.
  Sai o stream que sobra só com espaço ou quebra de linha, como o ``\n``
  que o tqdm escreve ao fechar a barra depois de um ``print``.

O ``metadata`` do notebook (kernel e ``language_info``), o ``execution_count``
e os demais outputs ficam como estão. O arquivo só é reescrito quando alguma
coisa muda, no formato do Jupyter (JSON com indentação 1 e chaves ordenadas).
``tests/test_limpar_notebooks.py`` cobre o script.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
NOTEBOOKS = RAIZ / "docs" / "notebooks"

# Tudo o que, na mesma linha, vem antes de um ``\r`` seguido de mais texto: o
# terminal sobrescreveria. Um ``\r`` no fim da linha (``\r\n``) fica.
_SOBRESCRITO = re.compile(r".*\r(?=[^\n])")
# Divide mantendo o ``\n`` no fim de cada linha, como o nbformat grava ``text``.
# ``str.splitlines`` não serve: também quebraria em ``\r``.
_LINHA = re.compile(r"[^\n]*\n|[^\n]+")


def _texto(saida: dict[str, Any]) -> str:
    """Devolve o ``text`` de uma saída ``stream`` como string única."""
    texto = saida.get("text", "")
    return texto if isinstance(texto, str) else "".join(texto)


def _eh_stream(saida: dict[str, Any]) -> bool:
    return saida.get("output_type") == "stream"


def limpar_saidas(saidas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    r"""Junta streams seguidos de mesmo nome e resolve os ``\r`` de cada linha."""
    juntas: list[dict[str, Any]] = []
    for saida in saidas:
        if (
            juntas
            and _eh_stream(saida)
            and _eh_stream(juntas[-1])
            and juntas[-1].get("name") == saida.get("name")
        ):
            juntas[-1]["text"] = _texto(juntas[-1]) + _texto(saida)
        else:
            juntas.append(copy.deepcopy(saida))

    limpas = []
    for saida in juntas:
        if _eh_stream(saida):
            texto = _SOBRESCRITO.sub("", _texto(saida))
            if not texto.strip():
                continue
            saida["text"] = _LINHA.findall(texto)
        limpas.append(saida)
    return limpas


def limpar_notebook(notebook: dict[str, Any]) -> dict[str, Any]:
    """Devolve uma cópia do notebook sem o ruído da execução."""
    limpo = copy.deepcopy(notebook)
    for celula in limpo.get("cells", []):
        celula.get("metadata", {}).pop("execution", None)
        if "outputs" in celula:
            celula["outputs"] = limpar_saidas(celula["outputs"])
    return limpo


def serializar(notebook: dict[str, Any]) -> str:
    """Serializa no formato que o Jupyter e o nbformat gravam."""
    return json.dumps(notebook, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def processar(caminho: Path, check: bool) -> bool:
    """Limpa um notebook; devolve ``True`` se ele tinha ruído."""
    notebook = json.loads(caminho.read_text(encoding="utf-8"))
    limpo = limpar_notebook(notebook)
    if limpo == notebook:
        return False
    if not check:
        caminho.write_text(serializar(limpo), encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    """Ponto de entrada da linha de comando."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "notebooks", nargs="*", type=Path, help="arquivos .ipynb; sem nenhum, todos de docs/notebooks/",
    )
    parser.add_argument("--check", action="store_true", help="só confere; sai com 1 se algum notebook mudaria")
    args = parser.parse_args(argv)

    caminhos = args.notebooks or sorted(NOTEBOOKS.glob("*.ipynb"))
    com_ruido = [caminho for caminho in caminhos if processar(caminho, args.check)]
    verbo = "tem ruído de execução" if args.check else "limpo"
    for caminho in com_ruido:
        nome = caminho.resolve().relative_to(RAIZ) if caminho.resolve().is_relative_to(RAIZ) else caminho
        print(f"{nome}: {verbo}", file=sys.stderr)
    return 1 if args.check and com_ruido else 0


if __name__ == "__main__":
    sys.exit(main())
