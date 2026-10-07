"""Build the TRF3 and TRF5 example notebooks with executed outputs.

Run from repo root::

    python scripts/build_trf_notebooks.py          # both notebooks
    python scripts/build_trf_notebooks.py trf3     # only TRF3

Writes ``docs/notebooks/trf3.ipynb`` and ``docs/notebooks/trf5.ipynb`` with
real outputs from a live cpopg lookup. Re-run whenever the scrapers change
their output shape so the docs stay in sync.
"""
from __future__ import annotations

import sys
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_NB = REPO_ROOT / "docs" / "notebooks"


def md(source: str) -> nbformat.NotebookNode:
    """Build a markdown notebook cell from ``source``."""
    return nbformat.v4.new_markdown_cell(source.strip("\n"))


def code(source: str) -> nbformat.NotebookNode:
    """Build a code notebook cell from ``source``."""
    return nbformat.v4.new_code_cell(source.strip("\n"))


def make_trf3() -> nbformat.NotebookNode:
    """Build the TRF3 cpopg/cposg notebook in-memory."""
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        md(
            """
# TRF3 — Tribunal Regional Federal da 3ª Região

Public process consultation for the federal courts of the third region (SP
and MS), through the JSON API behind the PJe public consultation apps:
[pje1g-consultapublica.trf3.jus.br](https://pje1g-consultapublica.trf3.jus.br/)
(first instance, `cpopg`) and
[pje2g-consultapublica.trf3.jus.br](https://pje2g-consultapublica.trf3.jus.br/)
(appeals, `cposg`).

| Feature | Available |
|---------|-----------|
| cpopg   | Yes       |
| cposg   | Yes       |
| cjsg    | No        |
| cjpg    | No        |
"""
        ),
        md("## Looking up a single process"),
        code(
            """
import juscraper as jus

trf3 = jus.scraper("trf3")
"""
        ),
        code(
            """
df = trf3.cpopg("5003536-21.2025.4.03.6342")
print(df.shape)
df[["id_cnj", "processo", "classe", "data_distribuicao", "orgao_julgador"]]
"""
        ),
        md("## Available columns"),
        code("df.columns.tolist()"),
        md(
            """
The scalar columns come first; `polo_ativo`, `polo_passivo`,
`outros_interessados`, `movimentacoes` and `documentos` are lists of dicts.
Paginated sections (movements are served 15 per page) are fetched in full.
"""
        ),
        md("## Inspecting movements"),
        code(
            """
movs = df.iloc[0]["movimentacoes"]
print(f"{len(movs)} events recorded")
for m in movs[:3]:
    print(f"  {m['data']} - {m['descricao']}")
"""
        ),
        md("## Inspecting parties"),
        code(
            """
for polo in ["polo_ativo", "polo_passivo"]:
    print(polo)
    for p in df.iloc[0][polo]:
        print(f"  - {p['nome']} ({p['tipo']})")
"""
        ),
        md(
            """
## Appeals (`cposg`)

`cposg` takes the same arguments and returns the same columns, querying the
second-instance app. An appeal usually keeps the CNJ number of the original
case; `orgao_julgador_colegiado` carries the panel (turma).
"""
        ),
        code(
            """
df_2g = trf3.cposg("5021122-65.2018.4.03.6100")
df_2g[["id_cnj", "processo", "classe", "orgao_julgador", "orgao_julgador_colegiado"]]
"""
        ),
        md(
            """
## Handling processes the public portal cannot return

When a CNJ does not surface in the public consultation (sealed or simply not
found), the row carries only `id_cnj`, so callers can still distinguish
"looked up but missing" from "never tried".
"""
        ),
        code(
            """
df_missing = trf3.cpopg("00000000020994030000")
df_missing
"""
        ),
        md(
            """
## Downloading the documents

With `download_pecas=True`, each listed document is saved as a PDF under
`<diretorio>/<cnj>/<id>.pdf`, and the `pecas` column lists the paths.
"""
        ),
        code(
            """
import tempfile
from pathlib import Path

df_pecas = trf3.cpopg("5003536-21.2025.4.03.6342", download_pecas=True, diretorio=tempfile.mkdtemp())
for caminho in df_pecas.iloc[0]["pecas"]:
    print(Path(caminho).parent.name, Path(caminho).stat().st_size, "bytes")
"""
        ),
        md(
            """
## Splitting download from parse

`cpopg_download` returns, per CNJ, a dict with the raw JSON envelopes of each
API route (or `None` when the process was not found); `cpopg_parse` turns that
list into the DataFrame. Useful to cache the raw responses before processing.
"""
        ),
        code(
            """
brutos = trf3.cpopg_download("5003536-21.2025.4.03.6342")
print(sorted(brutos[0]))

df_again = trf3.cpopg_parse(brutos, ["50035362120254036342"])
df_again[["id_cnj", "processo", "data_distribuicao"]]
"""
        ),
    ]
    nb.metadata.update(
        {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        }
    )
    return nb


def make_trf5() -> nbformat.NotebookNode:
    """Build the TRF5 cpopg notebook in-memory."""
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        md(
            """
# TRF5 — Tribunal Regional Federal da 5ª Região

Public process consultation (`cpopg`) for the federal courts under the
fifth region (AL, CE, PB, PE, RN, SE), via the PJe `ConsultaPublica`
system at
[pje1g.trf5.jus.br/pjeconsulta/](https://pje1g.trf5.jus.br/pjeconsulta/ConsultaPublica/listView.seam).

| Feature | Available |
|---------|-----------|
| cpopg   | Yes       |
| cposg   | No        |
| cjsg    | No        |
| cjpg    | No        |
"""
        ),
        md("## Looking up a single process"),
        code(
            """
import juscraper as jus

trf5 = jus.scraper("trf5")
"""
        ),
        code(
            """
df = trf5.cpopg("0058457-31.2025.4.05.8000")
print(df.shape)
df[["id_cnj", "processo", "classe", "orgao_julgador"]]
"""
        ),
        md("## Available columns"),
        code("df.columns.tolist()"),
        md(
            """
The first three columns are the canonical scalars; the trailing four are
list-typed and carry the nested arrays (parties, movements, attached
documents).
"""
        ),
        md("## Inspecting movements"),
        code(
            """
movs = df.iloc[0]["movimentacoes"]
print(f"{len(movs)} events recorded")
for m in movs[:5]:
    print(f"  {m['data']} - {m['descricao']}")
"""
        ),
        md("## Inspecting parties"),
        code(
            """
print("Polo ativo:")
for p in df.iloc[0]["polo_ativo"]:
    print(f"  - {p['participante']}")

print()
print("Polo passivo:")
for p in df.iloc[0]["polo_passivo"]:
    print(f"  - {p['participante']}")
"""
        ),
        md("## Looking up multiple processes at once"),
        code(
            """
cnjs = [
    "00584573120254058000",
    "00412666120254058100",
]
df_batch = trf5.cpopg(cnjs)
df_batch[["id_cnj", "processo", "classe", "orgao_julgador"]]
"""
        ),
        md(
            """
## Handling processes the public portal cannot return

When a CNJ does not surface in the public consultation (sigilo, archived,
or simply not found), the row carries only `id_cnj`. The other columns
come back as `None`/`NaN`, so callers can still distinguish "looked up
but missing" from "never tried".
"""
        ),
        code(
            """
import pandas as pd

df_missing = trf5.cpopg("00000000020994050000")
print("processo:", df_missing.iloc[0].get("processo"))
print("classe:", df_missing.iloc[0].get("classe"))
"""
        ),
        md(
            """
## Splitting download from parse

`cpopg` is a thin wrapper over `cpopg_download` (raw HTML) +
`cpopg_parse` (HTML → DataFrame). Splitting them is useful when you
want to cache the raw HTMLs to disk before processing.
"""
        ),
        code(
            """
htmls = trf5.cpopg_download("0058457-31.2025.4.05.8000")
print(f"got {len(htmls)} HTML(s), {len(htmls[0])} chars")

df_again = trf5.cpopg_parse(htmls, ["00584573120254058000"])
df_again[["id_cnj", "processo", "data_distribuicao"]]
"""
        ),
    ]
    nb.metadata.update(
        {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        }
    )
    return nb


def execute_and_save(nb: nbformat.NotebookNode, path: Path) -> None:
    """Execute the notebook and write it to ``path``."""
    print(f"executing {path.name} ...")
    ep = ExecutePreprocessor(timeout=180, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(path.parent)}})
    nbformat.write(nb, str(path))
    print(f"  wrote {path}")


def main(tribunais: list[str] | None = None) -> None:
    """Build and execute the TRF3 and TRF5 documentation notebooks.

    ``tribunais`` limits the run (e.g. ``["trf3"]``); default builds both.
    """
    DOCS_NB.mkdir(parents=True, exist_ok=True)
    builders = {"trf3": make_trf3, "trf5": make_trf5}
    for nome in tribunais or list(builders):
        execute_and_save(builders[nome](), DOCS_NB / f"{nome}.ipynb")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
