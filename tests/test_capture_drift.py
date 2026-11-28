"""Lint anti-drift para ``tests/fixtures/capture/<sigla>.py``.

Todo script de captura precisa montar as requisicoes com o codigo do raspador,
e nao com ``BASE_URL``/payload redefinidos inline (item 13 do checklist em
``CONTRIBUTING.md``). Vale uma destas formas:

- importar de ``juscraper.courts.<sigla>``/``juscraper.aggregators.<sigla>``, ou de
  um pacote de familia (``_esaj``, ``_trf``...) que o raspador herda;
- chamar o proprio raspador (``jus.scraper("<sigla>")``);
- usar um helper de captura de ``_util`` (``capture_*``, ``make_*``, ``fetch_*``),
  que monta o pedido com o codigo da familia. Os demais (``dump``,
  ``samples_dir_for``, ``build_session``...) nao montam o pedido e nao contam.

O arquivo se chama ``<sigla>.py`` ou ``<sigla>_<endpoint>.py``, com a sigla de um
raspador registrado; outro nome reprova.
"""
import ast
from pathlib import Path

import pytest

from juscraper import _SCRAPERS
from tests._helpers import classe_da_sigla

CAPTURE_DIR = Path(__file__).parent / "fixtures" / "capture"
SCRIPTS = sorted(p for p in CAPTURE_DIR.glob("*.py") if not p.name.startswith("_"))
#: Prefixos dos helpers de ``_util`` que montam o pedido com o codigo da familia.
_HELPERS_DE_CAPTURA = ("capture_", "make_", "fetch_")


def _sigla(path: Path) -> str:
    sigla = path.stem if path.stem in _SCRAPERS else path.stem.rsplit("_", 1)[0]
    assert sigla in _SCRAPERS, f"{path.name}: nome fora do padrao <sigla>.py ou <sigla>_<endpoint>.py"
    return sigla


def _pacotes_aceitos(sigla: str) -> set[str]:
    """Pacote do raspador e pacotes de familia (``juscraper.courts._esaj``...) da hierarquia dele."""
    raspador = classe_da_sigla(sigla)
    pacotes = {".".join(raspador.__module__.split(".")[:3])}
    for classe in raspador.__mro__:
        partes = classe.__module__.split(".")
        if len(partes) >= 3 and partes[2].startswith("_"):
            pacotes.add(".".join(partes[:3]))
    return pacotes


def _modulos_importados(tree: ast.Module) -> set[str]:
    modulos = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    modulos |= {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
    }
    return modulos


def _helpers_de_util(tree: ast.Module) -> set[str]:
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.level >= 1 and node.module == "_util"
        for alias in node.names
    }


def _raspadores_chamados(tree: ast.Module) -> set[str]:
    """Siglas literais de ``jus.scraper("...")``/``juscraper.scraper("...")``/``scraper("...")``."""
    siglas = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func, primeiro = node.func, node.args[0]
        nome = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if nome == "scraper" and isinstance(primeiro, ast.Constant) and isinstance(primeiro.value, str):
            siglas.add(primeiro.value)
    return siglas


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.stem)
def test_capture_usa_o_codigo_do_raspador(path: Path) -> None:
    sigla = _sigla(path)
    tree = ast.parse(path.read_text())
    pacotes = _pacotes_aceitos(sigla)

    importa_raspador = any(
        modulo == pacote or modulo.startswith(f"{pacote}.")
        for modulo in _modulos_importados(tree)
        for pacote in pacotes
    )
    usa_helper_de_captura = any(nome.startswith(_HELPERS_DE_CAPTURA) for nome in _helpers_de_util(tree))
    chama_o_raspador = sigla in _raspadores_chamados(tree)

    assert importa_raspador or usa_helper_de_captura or chama_o_raspador, (
        f"{path.name} nao importa de {sorted(pacotes)}, nao chama jus.scraper({sigla!r}) e nao usa "
        "helper de captura de _util. Risco de drift entre o payload da captura e o do raspador "
        "(item 13 do checklist em CONTRIBUTING.md): importe BASE_URL/build_<endpoint>_payload do "
        "download do raspador."
    )
