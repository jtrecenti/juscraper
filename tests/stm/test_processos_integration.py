"""Testes ao vivo do listar_processos do STM (precisam de rede).

O WAF do portal recusa pedidos conforme o IP de origem; com o marker
``anti_bot``, esse bloqueio vira ``xfail`` e qualquer outra falha continua
reprovando.
"""
import pytest

import juscraper as jus
from juscraper.courts.stm.download import RESULTS_PER_PAGE

pytestmark = [pytest.mark.integration, pytest.mark.anti_bot]


@pytest.fixture(scope="module")
def stm():
    return jus.scraper("stm")


def test_processo_por_numero_ao_vivo(stm):
    df = stm.listar_processos("7000374-06.2020.7.00.0000")

    assert df["processo"].tolist() == ["7000374-06.2020.7.00.0000"]
    linha = df.iloc[0]
    assert linha["classe"] == "HABEAS CORPUS CRIMINAL"
    assert linha["orgao"] == "SUPERIOR TRIBUNAL MILITAR"
    assert linha["data_autuacao"].year == 2020
    assert linha["partes"]
    assert linha["representantes"]
    assert linha["url_processo"].startswith("https://")


def test_duas_paginas_com_filtro_ao_vivo(stm):
    df = stm.listar_processos(orgao="SUPERIOR TRIBUNAL MILITAR", situacao="BAIXADO", paginas=2)

    assert len(df) == 2 * RESULTS_PER_PAGE
    assert df["processo"].is_unique
    assert set(df["orgao"]) == {"SUPERIOR TRIBUNAL MILITAR"}
    assert set(df["situacao"]) == {"BAIXADO"}
    # O portal ordena da autuação mais recente para a mais antiga.
    assert df["data_autuacao"].dropna().is_monotonic_decreasing


def test_filtros_das_auditorias_ao_vivo(stm):
    """``cjm`` e ``conselho`` só existem na 1ª instância."""
    df = stm.listar_processos(
        cjm="11ª CIRCUNSCRIÇÃO JUDICIÁRIA MILITAR - DF", classe="INQUÉRITO POLICIAL MILITAR", paginas=1
    )
    do_conselho = stm.listar_processos(conselho="CONSELHO PERMANENTE DE JUSTIÇA - EXÉRCITO", paginas=1)

    assert len(df) > 0
    assert set(df["classe"]) == {"INQUÉRITO POLICIAL MILITAR"}
    assert df["orgao"].str.contains("11ª CJM").all()
    assert len(do_conselho) > 0
    assert set(do_conselho["conselho"]) == {"CONSELHO PERMANENTE DE JUSTIÇA - EXÉRCITO"}


def test_numero_parcial_ao_vivo(stm):
    df = stm.listar_processos("7000374-06.2020", paginas=1)

    assert "7000374-06.2020.7.00.0000" in set(df["processo"])


def test_sem_resultados_ao_vivo(stm):
    df = stm.listar_processos("9999999-99.1900.7.00.0000")

    assert df.empty
