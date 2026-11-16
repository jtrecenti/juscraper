"""Testes ao vivo do cjsg do STM (precisam de rede).

O WAF do portal recusa pedidos conforme o IP de origem; com o marker
``anti_bot``, esse bloqueio vira ``xfail`` e qualquer outra falha continua
reprovando.
"""
import datetime

import pytest

import juscraper as jus
from juscraper.courts.stm.download import RESULTS_PER_PAGE

pytestmark = [pytest.mark.integration, pytest.mark.anti_bot]


@pytest.fixture(scope="module")
def stm():
    return jus.scraper("stm")


def test_cjsg_duas_paginas_ao_vivo(stm):
    df = stm.cjsg("deserção", paginas=2)

    assert len(df) == 2 * RESULTS_PER_PAGE
    assert df["id_documento"].is_unique
    assert df[["processo", "classe", "relator", "data_julgamento"]].notna().all().all()
    # O portal ordena do julgamento mais recente para o mais antigo.
    assert df["data_julgamento"].is_monotonic_decreasing


def test_cjsg_filtros_ao_vivo(stm):
    df = stm.cjsg("deserção", paginas=1, classe="APELAÇÃO", campo="inteiro_teor")

    assert len(df) > 0
    assert set(df["classe"]) == {"APELAÇÃO"}


def test_cjsg_por_numero_ao_vivo(stm):
    df = stm.cjsg("7000612-54.2022.7.00.0000", campo="numero")

    assert "7000612-54.2022.7.00.0000" in set(df["processo"])


def test_cjsg_sem_resultados_ao_vivo(stm):
    df = stm.cjsg("juscraper_probe_zero_hits_xyzqwe")

    assert df.empty


def test_cjsg_intervalo_de_julgamento_ao_vivo(stm):
    """Termo e intervalo juntos: a combinação que só a pesquisa avançada faz."""
    inicio, fim = datetime.date(2024, 1, 1), datetime.date(2024, 12, 31)

    com_data = stm.cjsg("deserção", data_julgamento_inicio=inicio, data_julgamento_fim=fim)

    assert len(com_data) > 0
    assert com_data["id_documento"].is_unique
    assert com_data["data_julgamento"].between(inicio, fim).all()
    assert com_data["ementa"].str.contains("deser", case=False).all()


def test_cjsg_intervalo_de_publicacao_ao_vivo(stm):
    inicio, fim = datetime.date(2024, 3, 1), datetime.date(2024, 3, 31)

    df = stm.cjsg("", paginas=1, data_publicacao_inicio=inicio, data_publicacao_fim=fim)

    assert len(df) > 0
    assert df["data_publicacao"].between(inicio, fim).all()


def test_cjsg_intervalo_sem_resultados_ao_vivo(stm):
    df = stm.cjsg("", data_julgamento_inicio="01/01/1800", data_julgamento_fim="31/12/1800")

    assert df.empty
