"""Build the TRF6 example notebook with executed outputs.

Run from repo root::

    python scripts/build_trf6_notebook.py

Writes ``docs/notebooks/trf6.ipynb`` with real outputs from a live cpopg
lookup. Re-run whenever the scraper changes its output shape so the docs
stay in sync. Each captcha solve downloads a HuggingFace pretrained CRNN
on first call (cached afterwards in the global ``huggingface_hub`` cache).
"""
from __future__ import annotations

from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_NB = REPO_ROOT / "docs" / "notebooks"


def md(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_markdown_cell(source.strip("\n"))


def code(source: str) -> nbformat.NotebookNode:
    return nbformat.v4.new_code_cell(source.strip("\n"))


def make_trf6() -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()
    nb.cells = [
        md(
            """
# TRF6 — Tribunal Regional Federal da 6ª Região

Public process consultation (`cpopg`) for the federal courts of Minas
Gerais (Seção Judiciária de MG), via the eproc system at
[eproc1g.trf6.jus.br/eproc/](https://eproc1g.trf6.jus.br/eproc/externo_controlador.php?acao=processo_consulta_publica).

The form is gated by a text-based image captcha that the backend **does**
validate; we solve it via the [`txtcaptcha`](https://github.com/jtrecenti/txtcaptcha)
package (HuggingFace pretrained CRNN, downloaded on first call). Each
captcha is bound to the session cookie, so a wrong solve triggers a fresh
form fetch + new captcha — controlled by the `max_captcha_attempts`
constructor parameter (default 3).

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

# `max_captcha_attempts` retries from a fresh form on each captcha rejection.
trf6 = jus.scraper("trf6", max_captcha_attempts=5)
"""
        ),
        code(
            """
df = trf6.cpopg("1005229-55.2023.4.06.3801")
print(df.shape)
df[["id_cnj", "processo", "classe", "data_autuacao"]]
"""
        ),
        md("## Available columns"),
        code("df.columns.tolist()"),
        md(
            """
The first six columns are the canonical scalars from the
"Capa do Processo" panel. The trailing five (`assuntos`, `polo_ativo`,
`polo_passivo`, `mpf`, `perito`, `movimentacoes`) are list-typed and
carry the nested arrays from the rest of the detail page.
"""
        ),
        md("## Inspecting movements"),
        code(
            """
movs = df.iloc[0]["movimentacoes"]
print(f"{len(movs)} events recorded")
for m in movs[:5]:
    print(f"  {m['evento']:>3} | {m['data_hora']} | {m['descricao'][:60]}")
"""
        ),
        md("## Inspecting parties"),
        code(
            """
print("Polo ativo:")
for p in df.iloc[0]["polo_ativo"]:
    print(f"  - {p['descricao'][:120]}")

print()
print("Polo passivo:")
for p in df.iloc[0]["polo_passivo"]:
    print(f"  - {p['descricao'][:120]}")
"""
        ),
        md(
            """
## Looking up multiple processes at once

Each lookup is one full request flow (form → captcha → search), so batches
are sequential — expect ~3–5 seconds per CNJ depending on captcha-solve
latency. Use `sleep_time` (default 1.0s) to throttle between calls.
"""
        ),
        code(
            """
cnjs = [
    "10052295520234063801",
    "10052379620234063812",
]
df_batch = trf6.cpopg(cnjs)
df_batch[["id_cnj", "processo", "classe"]]
"""
        ),
        md(
            """
## Handling processes the public portal cannot return

When a CNJ does not surface in the public consultation (sigilo, archived,
or simply not found), eproc re-serves the form silently with no error
message. The scraper detects that and yields a row with only `id_cnj`
populated — callers can still distinguish "looked up but missing" from
"never tried".
"""
        ),
        code(
            """
import pandas as pd

df_missing = trf6.cpopg("00000000020994060000")
print("processo:", df_missing.iloc[0].get("processo"))
print("classe:", df_missing.iloc[0].get("classe"))
"""
        ),
        md(
            """
## Splitting download from parse

`cpopg` is a thin wrapper over `cpopg_download` (raw HTML) +
`cpopg_parse` (HTML → DataFrame). Splitting them is useful when you
want to cache the raw HTMLs to disk before processing — relevant for
TRF6 because each download spends a captcha solve.
"""
        ),
        code(
            """
htmls = trf6.cpopg_download("1005229-55.2023.4.06.3801")
print(f"got {len(htmls)} HTML(s), {len(htmls[0])} chars")

df_again = trf6.cpopg_parse(htmls, ["10052295520234063801"])
df_again[["id_cnj", "processo", "data_autuacao"]]
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


def main() -> None:
    DOCS_NB.mkdir(parents=True, exist_ok=True)
    nb = make_trf6()
    path = DOCS_NB / "trf6.ipynb"
    print(f"executing {path.name} ...")
    ep = ExecutePreprocessor(timeout=300, kernel_name="python3")
    ep.preprocess(nb, {"metadata": {"path": str(path.parent)}})
    nbformat.write(nb, str(path))
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
