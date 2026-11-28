"""Gate da referência do quartodoc: todo raspador registrado tem página, com os métodos que oferece.

A referência só publica as classes listadas em ``quartodoc.sections`` de
``docs/_quarto.yml``, e, sem ``include_inherited: true``, só os métodos
definidos na própria classe. O ``quartodoc build`` passa nos dois casos: a
página do TJAC saía só com a docstring da classe, sem o ``cjsg`` herdado de
``_esaj/``, e TRF1, STF e Comunica CNJ não tinham página. A regra está no
CONTRIBUTING, em "Docstrings de métodos públicos com kwargs".
"""

from pathlib import Path

import pytest
import yaml

from juscraper import _SCRAPERS
from tests._helpers import classe_da_sigla

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _publicadas() -> dict[str, bool]:
    """Caminho de cada objeto da referência -> se publica os métodos herdados."""
    config = yaml.safe_load((DOCS / "_quarto.yml").read_text(encoding="utf-8"))
    publicadas: dict[str, bool] = {}
    for secao in config["quartodoc"]["sections"]:
        for item in secao["contents"]:
            if isinstance(item, str):
                publicadas[f"juscraper.{item}"] = False
            else:
                publicadas[f"juscraper.{item['name']}"] = bool(item.get("include_inherited", False))
    return publicadas


def metodos_herdados(classe: type) -> list[str]:
    """Métodos públicos que a classe herda de outra classe do pacote, fora de ``juscraper.core``.

    Os de ``juscraper.core`` (``set_verbose``, ``set_download_path``) são
    infraestrutura comum a todos os raspadores e ficam fora da página.
    """
    herdados = []
    for nome in dir(classe):
        if nome.startswith("_") or nome in vars(classe) or not callable(getattr(classe, nome)):
            continue
        dono = next(base for base in classe.__mro__ if nome in vars(base))
        if dono.__module__.startswith("juscraper.") and not dono.__module__.startswith("juscraper.core."):
            herdados.append(nome)
    return sorted(herdados)


PUBLICADAS = _publicadas()


@pytest.mark.parametrize("sigla", sorted(_SCRAPERS))
def test_raspador_registrado_tem_pagina_com_os_metodos(sigla):
    classe = classe_da_sigla(sigla)
    caminho = f"{classe.__module__}.{classe.__qualname__}"
    assert caminho in PUBLICADAS, (
        f"{caminho} (sigla {sigla!r}) não está em quartodoc.sections de docs/_quarto.yml; "
        "a referência não tem página para ele."
    )
    herdados = metodos_herdados(classe)
    assert not herdados or PUBLICADAS[caminho], (
        f"{caminho} herda {herdados}, que a página omite: declarar a entrada como "
        f"`- name: {caminho.removeprefix('juscraper.')}` com `include_inherited: true`."
    )


def test_metodos_herdados_ignora_os_da_propria_classe_e_do_core():
    class Base:
        def cjsg(self):
            """Busca."""

    Base.__module__ = "juscraper.courts._familia.base"

    class Raspador(Base):
        def cpopg(self):
            """Consulta."""

    assert metodos_herdados(Raspador) == ["cjsg"]
