"""Datas canonicas nas assinaturas publicas aceitam ``datetime.date``.

O pipeline de input converte ``datetime.date``/``datetime.datetime`` para o
formato do backend antes do pydantic, entao todo metodo publico que declara
``data_julgamento_*`` ou ``data_publicacao_*`` aceita ``date`` em runtime. A
anotacao precisa dizer o mesmo (``str | date | None``), senao o mypy do usuario
reprova uma chamada que funciona. O schema fica com ``str | None``; o motivo
esta em :class:`juscraper.schemas.DataJulgamentoMixin`.
"""
from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from datetime import date

import pytest

from juscraper.utils.params import DATE_CANONICAL
from tests.schemas.test_schema_coverage import _iter_aggregator_scrapers, _iter_court_scrapers

DATAS_CANONICAS = frozenset(DATE_CANONICAL)


def _casos() -> list[tuple[str, str, str, Callable[..., object]]]:
    return [
        (sigla, nome, parametro, metodo)
        for sigla, cls in [*_iter_court_scrapers(), *_iter_aggregator_scrapers()]
        for nome, metodo in inspect.getmembers(cls, inspect.isfunction)
        if not nome.startswith("_")
        for parametro in sorted(DATAS_CANONICAS & inspect.signature(metodo).parameters.keys())
    ]


CASOS = _casos()


def test_ha_metodos_com_datas_explicitas():
    assert len(CASOS) > 20


@pytest.mark.parametrize(
    ("sigla", "metodo_nome", "parametro", "metodo"),
    CASOS,
    ids=[f"{s}.{m}.{p}" for s, m, p, _ in CASOS],
)
def test_data_canonica_anotada_com_date(sigla, metodo_nome, parametro, metodo):
    anotacao = typing.get_type_hints(metodo)[parametro]
    assert date in typing.get_args(anotacao), (
        f"{sigla}.{metodo_nome}({parametro}) esta anotado como {anotacao}, mas o "
        "pipeline aceita datetime.date: anote str | date | None."
    )
