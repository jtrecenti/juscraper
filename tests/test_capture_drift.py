"""Lint anti-drift para ``tests/fixtures/capture/<sigla>.py``.

Todo script de captura precisa montar as requisicoes com o codigo do raspador,
e nao com ``BASE_URL``/payload redefinidos inline (item 13 do checklist em
``CONTRIBUTING.md``). Vale uma destas formas:

- importar de ``juscraper.courts.<sigla>``/``juscraper.aggregators.<sigla>`` ou de
  um pacote de familia (``juscraper.courts._esaj``, ``juscraper.courts._trf``...);
- chamar o proprio raspador (``jus.scraper(...)``);
- usar o helper compartilhado ``_util``, que importa a familia eSAJ.

O nome do arquivo e a sigla do raspador, com sufixo opcional por endpoint
(``tjmg_cposg.py``, ``trf3_cjsg.py``); script cuja sigla nao e um raspador
registrado reprova.
"""
import ast
from pathlib import Path

import pytest

from juscraper import _SCRAPERS

CAPTURE_DIR = Path(__file__).parent / "fixtures" / "capture"
SCRIPTS = sorted(p for p in CAPTURE_DIR.glob("*.py") if not p.name.startswith("_"))


def _sigla(path: Path) -> str:
    sigla = path.stem if path.stem in _SCRAPERS else path.stem.rsplit("_", 1)[0]
    assert sigla in _SCRAPERS, f"{path.name}: {sigla!r} nao e sigla de raspador registrado em juscraper._SCRAPERS"
    return sigla


def _chama_o_raspador(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "scraper"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"jus", "juscraper"}
        for node in ast.walk(tree)
    )


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_capture_usa_o_codigo_do_raspador(path: Path) -> None:
    sigla = _sigla(path)
    tree = ast.parse(path.read_text())
    imports = [(node.module or "", node.level) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    pacotes = (
        f"juscraper.courts.{sigla}",
        f"juscraper.aggregators.{sigla}",
        "juscraper.courts._",
        "juscraper.aggregators._",
    )

    importa_raspador = any(level == 0 and module.startswith(pacotes) for module, level in imports)
    usa_util = any(level >= 1 and module == "_util" for module, level in imports)

    assert importa_raspador or usa_util or _chama_o_raspador(tree), (
        f"{path.name} nao importa de juscraper.*.{sigla} nem de uma familia, nao chama "
        "jus.scraper() e nao usa _util. Risco de drift entre o payload da captura e o do "
        f"raspador (item 13 do checklist em CONTRIBUTING.md): importe BASE_URL/"
        f"build_<endpoint>_payload do download do raspador."
    )
