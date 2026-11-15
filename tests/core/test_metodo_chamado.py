"""Rótulo do método chamado no ``TypeError`` por kwarg desconhecido (#263).

``cjsg``/``cjpg`` delegam a ``*_download``, onde os kwargs são validados; a
mensagem precisa citar o método que o usuário chamou, em todo raspador.
"""
from importlib import import_module

import pytest
import responses

import juscraper as jus
from juscraper import _SCRAPERS
from tests._helpers import assert_unknown_kwarg_raises


def _classe(sigla):
    modulo, nome = _SCRAPERS[sigla].split(":")
    return getattr(import_module(modulo), nome)


_WRAPPERS = [
    (sigla, metodo)
    for sigla in sorted(_SCRAPERS)
    for metodo in ("cjsg", "cjpg")
    if hasattr(_classe(sigla), f"{metodo}_download")
]


@pytest.mark.parametrize(("sigla", "metodo"), _WRAPPERS, ids=[f"{s}.{m}" for s, m in _WRAPPERS])
@responses.activate
def test_wrapper_e_download_citam_o_metodo_chamado(sigla, metodo):
    scraper = jus.scraper(sigla)
    classe = type(scraper).__name__

    assert_unknown_kwarg_raises(
        getattr(scraper, metodo), "kwarg_inventado", "dano moral", paginas=1, rotulo=f"{classe}.{metodo}()"
    )
    # Depois do erro no wrapper, o contexto foi restaurado: a chamada direta cita o download.
    assert_unknown_kwarg_raises(
        getattr(scraper, f"{metodo}_download"),
        "kwarg_inventado",
        "dano moral",
        paginas=1,
        rotulo=f"{classe}.{metodo}_download()",
    )


def test_outro_rotulo_validado_dentro_do_wrapper_fica_intacto():
    """``cjsg(count_only=True)`` valida com rótulo próprio, que não é trocado."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjac").cjsg,
        "kwarg_inventado",
        "dano moral",
        count_only=True,
        rotulo="TJACScraper.cjsg(count_only=True)",
    )
