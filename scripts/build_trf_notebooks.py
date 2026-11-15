"""Build the TRF3 and TRF5 example notebooks with executed outputs.

Run from repo root::

    python scripts/build_trf_notebooks.py          # both notebooks
    python scripts/build_trf_notebooks.py trf3     # only TRF3

Writes ``docs/notebooks/trf3.ipynb`` and ``docs/notebooks/trf5.ipynb`` with
real outputs from live lookups (``cpopg``/``cposg`` and, in TRF3, ``cjsg``). Re-run whenever the scrapers change
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
    """Build the TRF3 cpopg/cposg/cjsg notebook in-memory."""
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
(appeals, `cposg`). Case-law search (`cjsg`) uses the separate portal at
[web.trf3.jus.br/jurisprudencia](https://web.trf3.jus.br/jurisprudencia/).

| Feature | Available |
|---------|-----------|
| cpopg   | Yes       |
| cposg   | Yes       |
| cjsg    | Yes       |
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
found), the row carries only `id_cnj`, with `motivo_falha` set to `None`. A
lookup that fails (network or HTTP error on the search or on `/dados` after
the retries, an unexpected response, a parser error) also yields a row with
only `id_cnj`, but `motivo_falha` names the reason (`timeout`, `conexao`,
`retry_esgotado_<status>`, `resposta_inesperada`), and the failures come in a
single `UserWarning` at the end. An Akamai block stops the batch: the blocked
CNJ and the following ones come back as `bloqueio_anti_bot`, without new
requests, under a `BloqueioAntiBotWarning`.
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
`<diretorio>/<cnj>/<id>.pdf`, and the `pecas` column lists the paths. The
documents that could not be downloaded go to `pecas_falhas`, as
`{"id": ..., "motivo_falha": ...}`.
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
API route (or `None` when the process was not found or the lookup failed,
with the failures in a `UserWarning`); `cpopg_parse` turns that list into the
DataFrame, without the `motivo_falha` column. Useful to cache the raw
responses before processing.
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
        md(
            """
## Searching case law (`cjsg`)

`cjsg` searches the TRF3 case-law portal at
[web.trf3.jus.br/jurisprudencia](https://web.trf3.jus.br/jurisprudencia/),
a system separate from the PJe. The `base` argument picks one of the four
result sets the portal keeps apart:

| `base` | Content |
|--------|---------|
| `"acordaos"` (default) | TRF3 appellate judgments |
| `"turmas_recursais"` | judgments of the federal small-claims appeal panels (JEF) |
| `"monocraticas"` | single-judge decisions of the TRF3 |
| `"monocraticas_turmas_recursais"` | single-judge decisions of the appeal panels |

Each call opens its own session on the portal and reads the result list,
which already carries the ementa and the full text of every document: the
cost is three fixed requests (opening the tab, the search POST and the GET of
its redirect, which is page 1) plus one per extra page, with `sleep_time`
between pages.
"""
        ),
        code(
            """
df_cjsg = trf3.cjsg(
    "medicamento",
    paginas=range(1, 3),
    data_julgamento_inicio="2026-01-01",
    data_julgamento_fim="2026-06-30",
)
print(df_cjsg.shape)
df_cjsg[["processo", "classe", "orgao_julgador", "relator", "data_julgamento", "meio_publicacao"]].head()
"""
        ),
        md(
            """
### The other bases

In the single-judge bases, `ementa` holds the text of the decision (there is
no ementa) and `orgao_julgador` is empty; `data_julgamento` is the date of the
decision.

In part of the older appeal-panel judgments (`turmas_recursais`), `ementa` is
null because the portal sends an empty ementa block; `inteiro_teor` still
carries the full text. When this was measured, every ementa from 2013 and 2014
was empty, and some from 2011.
"""
        ),
        code(
            """
for base in ["turmas_recursais", "monocraticas", "monocraticas_turmas_recursais"]:
    df_base = trf3.cjsg(
        "medicamento",
        base=base,
        paginas=1,
        data_julgamento_inicio="2026-01-01",
        data_julgamento_fim="2026-06-30",
    )
    print(base, df_base.shape, df_base["relator"].iloc[0])
"""
        ),
        md(
            """
### Filters

`relator` and `classe` are free text matched against the
portal's index, not dropdown IDs. Use the spelling of the form's dropdowns:
`relator="NERY JUNIOR"`, `classe="AI - AGRAVO DE INSTRUMENTO"`.

`orgao_julgador` picks one option of the órgão dropdown of the tab, by its
label (`"3ª Turma"`, `"11ª Turma Recursal da Seção Judiciária de São Paulo"`)
or by its indexed name (`"TERCEIRA TURMA"`, `"11ª TURMA RECURSAL DE SÃO
PAULO"`), ignoring case and spacing. The value in the `orgao_julgador` column
also works: as in the portal's form, `"1a. seção"` becomes `"1A"`, so `"QUINTA
TURMA - 1A. SEÇÃO"` matches the option `QUINTA TURMA - 1a. SEÇÃO`. The search
reads the dropdown from the tab it already opens and sends the pair the browser
sends, the label and the indexed name of the option, and the portal returns the
documents recorded under either (measured with "medicamento": `"QUINTA TURMA"`
finds 576 documents, against 443 for the label alone and 133 for the indexed
name alone). A label shared by more than one option, such as `"5ª Turma"` in
the acórdãos base, raises `ValueError` listing the indexed names that resolve
it; text that matches no option is sent as is and only finds what the portal
records with that spelling. The monocratic bases have no órgão filter.

The form has a single date pair, so pass either `data_julgamento_*` or
`data_publicacao_*`, not both.
"""
        ),
        code(
            """
df_filtrado = trf3.cjsg(
    "medicamento",
    relator="NERY JUNIOR",
    classe="AI - AGRAVO DE INSTRUMENTO",
    data_publicacao_inicio="2026-01-01",
    data_publicacao_fim="2026-06-30",
    paginas=1,
)
df_filtrado[["processo", "relator", "relator_acordao", "data_publicacao"]]
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
