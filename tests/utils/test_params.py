"""Unit tests for date-related helpers in :mod:`juscraper.utils.params`."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from juscraper.utils.params import OPEN_ENDED_DATE_FLOOR_BR, coerce_brazilian_date, fill_open_ended_dates


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


# --- fill_open_ended_dates ----------------------------------------------------
# Refs bug do TJSP cjpg: o backend eSAJ recebia ``dadosConsulta.dtFim=`` vazio
# quando o usuário passava só ``data_julgamento_inicio`` e devolvia ``tudo
# desde X até hoje``, fazendo o paginador iterar sobre dezenas de milhares de
# páginas. O auto-fill substitui a data ausente por um valor pragmático e
# emite ``UserWarning`` para o usuário consciente do que aconteceu.


def test_fill_open_ended_only_inicio_brazilian():
    """Só ``_inicio`` em BR → ``_fim`` vira data atual em ``DD/MM/AAAA``."""
    hoje = date.today().strftime("%d/%m/%Y")
    datas = {"data_julgamento_inicio": "01/01/2024", "data_julgamento_fim": None}
    with pytest.warns(UserWarning, match=r"data_julgamento_fim"):
        fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_julgamento")
    assert datas == {"data_julgamento_inicio": "01/01/2024", "data_julgamento_fim": hoje}


def test_fill_open_ended_only_inicio_iso():
    """Só ``_inicio`` em ISO → ``_fim`` vira data atual em ``AAAA-MM-DD``."""
    hoje = date.today().strftime("%Y-%m-%d")
    datas = {"data_julgamento_inicio": "2024-01-01", "data_julgamento_fim": None}
    with pytest.warns(UserWarning):
        fill_open_ended_dates(datas, formato="%Y-%m-%d", rotulo="data_julgamento")
    assert datas["data_julgamento_fim"] == hoje


def test_fill_open_ended_only_fim_brazilian():
    """Só ``_fim`` em BR → ``_inicio`` vira ``01/01/1990``."""
    datas = {"data_julgamento_inicio": None, "data_julgamento_fim": "31/12/2024"}
    with pytest.warns(UserWarning, match=r"01/01/1990"):
        fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_julgamento")
    assert datas == {"data_julgamento_inicio": "01/01/1990", "data_julgamento_fim": "31/12/2024"}


def test_fill_open_ended_only_fim_iso():
    """Só ``_fim`` em ISO → ``_inicio`` vira ``1990-01-01``."""
    datas = {"data_julgamento_inicio": None, "data_julgamento_fim": "2024-12-31"}
    with pytest.warns(UserWarning, match=r"1990-01-01"):
        fill_open_ended_dates(datas, formato="%Y-%m-%d", rotulo="data_julgamento")
    assert datas["data_julgamento_inicio"] == "1990-01-01"


def test_fill_open_ended_both_present_passthrough():
    """Ambos preenchidos → noop, sem warning, idempotente em segunda chamada."""
    datas = {"data_julgamento_inicio": "01/01/2024", "data_julgamento_fim": "31/12/2024"}
    snapshot = dict(datas)
    # Sem warning (filterwarnings=error reverte UserWarning em erro)
    fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_julgamento")
    fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_julgamento")  # idempotente
    assert datas == snapshot


def test_fill_open_ended_both_none_passthrough():
    """Ambos ``None`` → noop, sem warning (busca aberta = sem filtro de data)."""
    datas = {"data_julgamento_inicio": None, "data_julgamento_fim": None}
    fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_julgamento")
    assert datas == {"data_julgamento_inicio": None, "data_julgamento_fim": None}


def test_fill_open_ended_publicacao_rotulo():
    """``rotulo="data_publicacao"`` opera no par certo, sem tocar julgamento."""
    hoje = date.today().strftime("%d/%m/%Y")
    datas = {
        "data_julgamento_inicio": None,
        "data_julgamento_fim": None,
        "data_publicacao_inicio": "01/01/2024",
        "data_publicacao_fim": None,
    }
    with pytest.warns(UserWarning, match=r"data_publicacao_fim"):
        fill_open_ended_dates(datas, formato="%d/%m/%Y", rotulo="data_publicacao")
    assert datas["data_publicacao_fim"] == hoje
    assert datas["data_julgamento_inicio"] is None
    assert datas["data_julgamento_fim"] is None


def test_open_ended_date_floor_constant():
    """A constante de floor é a data zero pragmática do judiciário digital."""
    assert OPEN_ENDED_DATE_FLOOR_BR == "01/01/1990"
