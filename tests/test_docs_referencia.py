"""Gate da referência do quartodoc: todo raspador registrado tem página, com os métodos que oferece.

A referência só publica as classes listadas em ``quartodoc.sections`` de
``docs/_quarto.yml``, e, sem ``include_inherited: true`` (nas ``options`` da
seção, como as seções de raspadores declaram, ou na entrada), só os métodos
definidos na própria classe. O ``quartodoc build`` passa nos dois casos: a
página do TJAC saía só com a docstring da classe, sem o ``cjsg`` herdado de
``_esaj/``, e TRF1, STF e Comunica CNJ não tinham página. A regra está no
CONTRIBUTING, item 16 de "Adding a new tribunal".
"""


import pytest

from juscraper import _SCRAPERS
from tests._helpers import classe_da_sigla, classes_publicadas


def metodos_herdados(classe: type) -> list[str]:
    """Métodos públicos que a classe herda de outra classe do pacote, fora de ``juscraper.core``.

    Os de ``juscraper.core`` (``set_verbose``, ``set_download_path``) são
    infraestrutura comum a todos os raspadores e o teste não os exige. Atributo
    de classe que é ele próprio uma classe, como o schema em ``INPUT_CJSG``, não
    conta como método.
    """
    herdados = []
    for nome in dir(classe):
        if nome.startswith("_") or nome in vars(classe):
            continue
        atributo = getattr(classe, nome)
        if isinstance(atributo, type) or not callable(atributo):
            continue
        dono = next(base for base in classe.__mro__ if nome in vars(base))
        if dono.__module__.startswith("juscraper.") and not dono.__module__.startswith("juscraper.core."):
            herdados.append(nome)
    return sorted(herdados)


PUBLICADAS = classes_publicadas()


@pytest.mark.parametrize("sigla", sorted(_SCRAPERS))
def test_raspador_registrado_tem_pagina_com_os_metodos(sigla):
    classe = classe_da_sigla(sigla)
    caminho = f"{classe.__module__}.{classe.__qualname__}"
    assert classe in PUBLICADAS, (
        f"{caminho} (sigla {sigla!r}) não está em quartodoc.sections de docs/_quarto.yml; "
        "a referência não tem página para ele."
    )
    herdados = metodos_herdados(classe)
    assert not herdados or PUBLICADAS[classe], (
        f"{caminho} herda {herdados}, que a página omite: a seção (ou a entrada) precisa de "
        "`include_inherited: true` em docs/_quarto.yml."
    )


def test_metodos_herdados_ignora_os_da_propria_classe_e_do_core():
    class Base:
        INPUT_CJSG = dict

        def cjsg(self):
            """Busca."""

    Base.__module__ = "juscraper.courts._familia.base"

    class Raspador(Base):
        def cpopg(self):
            """Consulta."""

    assert metodos_herdados(Raspador) == ["cjsg"]
