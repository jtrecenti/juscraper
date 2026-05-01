"""Unit tests for date-related helpers in :mod:`juscraper.utils.params`."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from juscraper.utils.params import coerce_brazilian_date


@pytest.mark.parametrize("entrada", [
    "01/03/2024",
    "01-03-2024",
    "2024-03-01",
    "2024/03/01",
])
def test_coerce_brazilian_date_to_br(entrada):
    """4 strings aceitas → coage para ``%d/%m/%Y``."""
    assert coerce_brazilian_date(entrada, "%d/%m/%Y") == "01/03/2024"


@pytest.mark.parametrize("entrada", [
    "01/03/2024",
    "01-03-2024",
    "2024-03-01",
    "2024/03/01",
])
def test_coerce_brazilian_date_to_iso(entrada):
    """4 strings aceitas → coage para ``%Y-%m-%d``."""
    assert coerce_brazilian_date(entrada, "%Y-%m-%d") == "2024-03-01"


def test_coerce_brazilian_date_aceita_date_object():
    """``datetime.date`` é coercido via ``strftime``."""
    assert coerce_brazilian_date(date(2024, 3, 1), "%d/%m/%Y") == "01/03/2024"
    assert coerce_brazilian_date(date(2024, 3, 1), "%Y-%m-%d") == "2024-03-01"


def test_coerce_brazilian_date_aceita_datetime_object():
    """``datetime.datetime`` é tratado como ``date`` (componente time descartado no strftime)."""
    assert coerce_brazilian_date(datetime(2024, 3, 1, 10, 30), "%d/%m/%Y") == "01/03/2024"
    assert coerce_brazilian_date(datetime(2024, 3, 1, 23, 59, 59), "%Y-%m-%d") == "2024-03-01"


@pytest.mark.parametrize("entrada", [None, ""])
def test_coerce_brazilian_date_passthrough_falsy(entrada):
    """``None`` e ``""`` passam direto — open-ended search."""
    assert coerce_brazilian_date(entrada, "%d/%m/%Y") == entrada
    assert coerce_brazilian_date(entrada, "%Y-%m-%d") == entrada


@pytest.mark.parametrize("entrada", [
    "01.03.2024",            # dotted (não suportado)
    "abc",                   # nonsense
    "2024-13-45",            # mês/dia inválidos
    "1/3/24",                # dia/mês 1-dígito + ano 2-dígitos
])
def test_coerce_brazilian_date_passthrough_irreconhecivel(entrada):
    """Formato fora dos 4 aceitos passa direto — validate_intervalo_datas decide."""
    assert coerce_brazilian_date(entrada, "%d/%m/%Y") == entrada


def test_coerce_brazilian_date_tipo_inesperado_passthrough():
    """Tipo não esperado (ex.: int) passa direto — validate decide."""
    assert coerce_brazilian_date(20240301, "%d/%m/%Y") == 20240301
