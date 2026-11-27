import subprocess
import sys
import typing

import juscraper
from juscraper import _SCRAPERS, scraper
from tests._helpers import classe_da_sigla


def test_scraper_factory_is_callable():
    assert callable(scraper)


def test_overloads_cobrem_o_mapa_de_siglas():
    """Cada sigla de `_SCRAPERS` tem uma overload `Literal[sigla]` que devolve a mesma classe.

    As overloads são o que o verificador de tipos de quem usa a biblioteca enxerga;
    o mapa é o que roda. Se alguém registrar um tribunal só num dos dois, este teste falha.
    """
    esperado = {sigla: classe_da_sigla(sigla) for sigla in _SCRAPERS}
    namespace = {**vars(juscraper), **{classe.__name__: classe for classe in esperado.values()}}

    dicas = [typing.get_type_hints(o, globalns=namespace) for o in typing.get_overloads(scraper)]

    # O fallback para `str` arbitrária (variável, maiúsculas) tem de ser a última:
    # overload de sigla depois dele seria inalcançável para o verificador.
    fallbacks = [i for i, d in enumerate(dicas) if d["sigla"] is str]
    assert fallbacks == [len(dicas) - 1], "o fallback `sigla: str` deve ser a última overload, e só uma"
    assert dicas[-1]["return"] is typing.Any

    por_sigla: dict[str, type] = {}
    for d in dicas[:-1]:
        (sigla,) = typing.get_args(d["sigla"])
        assert sigla not in por_sigla, f"overload repetida para {sigla!r}"
        por_sigla[sigla] = d["return"]

    assert por_sigla == esperado


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
