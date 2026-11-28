"""Meta-teste: os mapas de :mod:`tests.schemas._registro` cobrem os endpoints publicos.

Varre ``juscraper.courts`` e ``juscraper.aggregators`` via reflexao e, para
cada metodo publico implementado (nao ``NotImplementedError``), confirma que
existe uma classe ``Input<Endpoint><Tribunal>`` mapeada em
``EXPECTED_COURT_SCHEMAS`` ou ``EXPECTED_AGGREGATOR_SCHEMAS``. Na direcao
oposta, reprova entrada do mapa cujo endpoint virou stub ou cujo raspador sumiu.

A manutencao dos mapas e explicita de proposito: quando alguem adiciona um
tribunal novo ou implementa um endpoint que antes era stub, o teste falha
ate o mapa ser atualizado. Isso impede que schemas fiquem "orfaos"
silenciosamente.

Stubs (``raise NotImplementedError``) sao detectados automaticamente por
inspecao do source; nao precisam entrar em nenhuma lista.
"""
from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.schemas._registro import (
    AGGREGATOR_ENDPOINTS,
    COURT_ENDPOINTS,
    EXPECTED_AGGREGATOR_SCHEMAS,
    EXPECTED_COURT_SCHEMAS,
    endpoints_implementados,
    raspadores_agregadores,
    raspadores_tribunais,
)

GRUPOS = [
    pytest.param(
        raspadores_tribunais, COURT_ENDPOINTS, EXPECTED_COURT_SCHEMAS, "EXPECTED_COURT_SCHEMAS", id="tribunais"
    ),
    pytest.param(
        raspadores_agregadores,
        AGGREGATOR_ENDPOINTS,
        EXPECTED_AGGREGATOR_SCHEMAS,
        "EXPECTED_AGGREGATOR_SCHEMAS",
        id="agregadores",
    ),
]


def _implementados(
    raspadores: Callable[[], dict[str, type]], candidatos: tuple[str, ...]
) -> set[tuple[str, str]]:
    return {
        (sigla, endpoint)
        for sigla, cls in raspadores().items()
        for endpoint in endpoints_implementados(cls, candidatos)
    }


@pytest.mark.parametrize(("raspadores", "candidatos", "mapa", "nome_mapa"), GRUPOS)
def test_endpoint_implementado_tem_schema(raspadores, candidatos, mapa, nome_mapa):
    faltam = sorted(_implementados(raspadores, candidatos) - mapa.keys())
    assert not faltam, f"Endpoints sem entrada em {nome_mapa}:\n" + "\n".join(f"{s}.{e}" for s, e in faltam)


@pytest.mark.parametrize(("raspadores", "candidatos", "mapa", "nome_mapa"), GRUPOS)
def test_mapa_sem_entradas_orfas(raspadores, candidatos, mapa, nome_mapa):
    """Impede que entradas sobrevivam depois que um endpoint vira stub ou o raspador some."""
    orfas = sorted(mapa.keys() - _implementados(raspadores, candidatos))
    assert not orfas, f"Entradas orfas em {nome_mapa} (remover):\n" + "\n".join(f"{s}.{e}" for s, e in orfas)
