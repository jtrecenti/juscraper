"""Meta-teste: os mapas de :mod:`tests.schemas._registro` cobrem os endpoints publicos.

Os candidatos saem das proprias classes: todo metodo publico implementado de um
raspador (:func:`~tests.schemas._registro.endpoints_publicos`) precisa de uma
classe ``Input*`` mapeada em ``EXPECTED_COURT_SCHEMAS`` ou
``EXPECTED_AGGREGATOR_SCHEMAS``, salvo os de ``FORA_DO_REGISTRO``, com o motivo,
e os ``<endpoint>_download``/``_parse``. Na direcao oposta, reprova entrada do
mapa cujo endpoint virou stub ou cujo raspador sumiu.

Metodo publico novo, tribunal novo ou endpoint que deixou de ser stub reprova o
teste ate o mapa ser atualizado. Stubs (``raise NotImplementedError``) sao
detectados pelo source e nao entram em lista nenhuma.
"""
from __future__ import annotations

from functools import cache

from tests.schemas._registro import (
    FORA_DO_REGISTRO,
    INPUT_SCHEMAS,
    OUTPUT_SCHEMAS,
    endpoints_publicos,
    metodos_publicos,
    raspadores,
    resolve,
    schemas_definidos,
)


@cache
def _implementados() -> set[tuple[str, str]]:
    return {(sigla, endpoint) for sigla, cls in raspadores().items() for endpoint in endpoints_publicos(cls)}


def test_endpoint_publico_tem_schema():
    faltam = sorted(_implementados() - INPUT_SCHEMAS.keys())
    assert not faltam, (
        "Metodos publicos sem entrada em EXPECTED_*_SCHEMAS (mapear o Input, ou registrar "
        "em FORA_DO_REGISTRO com o motivo):\n" + "\n".join(f"{s}.{e}" for s, e in faltam)
    )


def test_mapa_sem_entradas_orfas():
    """Impede que entradas sobrevivam depois que um endpoint vira stub ou o raspador some."""
    orfas = sorted(INPUT_SCHEMAS.keys() - _implementados())
    assert not orfas, "Entradas orfas em EXPECTED_*_SCHEMAS (remover):\n" + "\n".join(f"{s}.{e}" for s, e in orfas)


def test_fora_do_registro_ainda_existe():
    existentes = {chave for cls in raspadores().values() for chave in metodos_publicos(cls).values()}
    sobram = sorted(FORA_DO_REGISTRO.keys() - existentes)
    assert not sobram, f"Entradas de FORA_DO_REGISTRO sem metodo publico (remover): {sobram}"


def test_atributo_input_bate_com_o_mapa():
    """``INPUT_<ENDPOINT>`` do raspador e o schema mapeado para ``(sigla, endpoint)``.

    O atributo e o que o metodo valida; se diverge do mapa, os testes daqui
    conferem um schema e o metodo usa outro.
    """
    divergentes = []
    for sigla, cls in raspadores().items():
        for nome in dir(cls):
            if not nome.startswith("INPUT_"):
                continue
            entrada = INPUT_SCHEMAS.get((sigla, nome.removeprefix("INPUT_").lower()))
            atributo = getattr(cls, nome)
            if entrada is None or atributo is not resolve(*entrada):
                divergentes.append(f"{sigla}.{nome} = {atributo!r}, mapa: {entrada}")
    assert not divergentes, "Atributos INPUT_* fora do mapa:\n" + "\n".join(divergentes)


def test_schema_publico_esta_mapeado():
    """Todo ``Input*``/``Output*`` publico dos modulos de schemas esta mapeado ou e base de um mapeado.

    Schema que ninguem mapeia nao passa por nenhum teste daqui (contrato, paridade,
    tipos canonicos) e tende a divergir do metodo em silencio.
    """
    mapeados = [resolve(*entrada) for mapa in (INPUT_SCHEMAS, OUTPUT_SCHEMAS) for entrada in mapa.values()]
    soltos = sorted(
        f"{schema.__module__}.{schema.__name__}"
        for schema in schemas_definidos()
        if schema.__name__.startswith(("Input", "Output"))
        and not any(issubclass(mapeado, schema) for mapeado in mapeados)
    )
    assert not soltos, "Schemas publicos sem entrada em EXPECTED_* (mapear ou remover):\n" + "\n".join(soltos)
