import subprocess
import sys
import typing
from importlib import import_module

import juscraper
from juscraper import _SCRAPERS, scraper


def test_scraper_factory_is_callable():
    assert callable(scraper)


def _classe(destino: str) -> type:
    modulo, nome = destino.split(":")
    classe: type = getattr(import_module(modulo), nome)
    return classe


def test_overloads_cobrem_o_mapa_de_siglas():
    """Cada sigla de `_SCRAPERS` tem uma overload `Literal[sigla]` que devolve a mesma classe.

    As overloads são o que o verificador de tipos de quem usa a biblioteca enxerga;
    o mapa é o que roda. Se alguém registrar um tribunal só num dos dois, este teste falha.
    """
    classes = {destino.split(":")[1]: _classe(destino) for destino in _SCRAPERS.values()}
    namespace = {**vars(juscraper), **classes}

    por_sigla: dict[str, type] = {}
    overloads = typing.get_overloads(scraper)
    for overload in overloads[:-1]:
        dicas = typing.get_type_hints(overload, globalns=namespace)
        (sigla,) = typing.get_args(dicas["sigla"])
        assert sigla not in por_sigla, f"overload repetida para {sigla!r}"
        por_sigla[sigla] = dicas["return"]

    assert por_sigla == {sigla: _classe(destino) for sigla, destino in _SCRAPERS.items()}

    # A última overload é o fallback para `str` arbitrária (variável, maiúsculas).
    fallback = typing.get_type_hints(overloads[-1], globalns=namespace)
    assert fallback["sigla"] is str
    assert fallback["return"] is typing.Any


def test_import_juscraper_nao_carrega_os_raspadores():
    """As classes das overloads vêm de imports sob `TYPE_CHECKING`; o import segue preguiçoso."""
    codigo = (
        "import sys, juscraper; "
        "print(sorted(m for m in sys.modules if m.startswith(('juscraper.courts', 'juscraper.aggregators'))))"
    )
    saida = subprocess.run(
        [sys.executable, "-c", codigo], capture_output=True, text=True, check=True
    ).stdout
    assert saida.strip() == "[]"
