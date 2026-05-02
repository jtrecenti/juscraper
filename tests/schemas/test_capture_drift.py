"""Lint anti-drift para tests/fixtures/capture/<xx>.py.

Garante que cada capture script importa pelo menos uma constante/funcao
publica do scraper correspondente (ou usa o helper compartilhado _util),
em vez de redefinir BASE_URL/payload inline. Cobre o cenario comum de
drift descrito no item 13 do checklist em CONTRIBUTING.md.
"""
import ast
from pathlib import Path

import pytest

CAPTURE_DIR = Path(__file__).parent.parent / "fixtures" / "capture"


def _capture_modules() -> list[Path]:
    return sorted(
        p for p in CAPTURE_DIR.glob("tj*.py")
        if not p.name.startswith("_")
    )


def _module_names(tree: ast.Module) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.append((node.module or "", node.level))
    return out


@pytest.mark.parametrize("path", _capture_modules(), ids=lambda p: p.stem)
def test_capture_imports_scraper_or_shared_util(path: Path) -> None:
    tribunal = path.stem
    tree = ast.parse(path.read_text())
    imports = _module_names(tree)

    has_scraper = any(
        level == 0 and (
            module.startswith(f"juscraper.courts.{tribunal}")
            or module.startswith("juscraper.courts._")
        )
        for module, level in imports
    )
    has_util = any(
        level >= 1 and module == "_util"
        for module, level in imports
    )

    assert has_scraper or has_util, (
        f"{path.name} nao importa de juscraper.courts.{tribunal}.* nem do "
        f"helper compartilhado _util. Risco de drift entre payload do "
        f"capture e payload real do scraper (item 13 do checklist em "
        f"CONTRIBUTING.md). Importe BASE_URL/build_<endpoint>_payload de "
        f"juscraper.courts.{tribunal}.download (ou via _util)."
    )
