"""Integração do ``cjsg`` do TJTO.

Do mesmo IP, o AWS WAF do portal deixa passar cerca de 7 buscas seguidas e
depois desafia ou pede CAPTCHA por 10 minutos ou mais, também de IP
residencial (15/11/2026). Por isso a suíte do TJTO, com ``test_cjpg.py``, faz
6 POSTs: as colunas, a paginação e o parse vêm de uma única busca de 2
páginas, e o resto do contrato (filtros no payload, ``paginas`` inteiro,
aliases) fica nos testes offline. Rodar a suíte duas vezes em menos de 10
minutos cai no bloqueio: ``BotChallengeBlockedError`` na primeira página, ou
``ColetaParcialError`` com ele em ``__cause__`` numa página seguinte.
"""
from datetime import date

import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjto.client import TJTOScraper

COLUNAS = {
    "processo", "uuid", "classe", "tipo_julgamento", "assunto",
    "competencia", "relator", "data_autuacao", "data_julgamento",
    "processo_link",
}


@pytest.mark.integration
def test_cjsg_duas_paginas_com_as_colunas_esperadas():
    """2 POSTs: as duas primeiras páginas de ``"direito"``, cruas e lidas."""
    scraper = jus.scraper("tjto")
    assert isinstance(scraper, TJTOScraper)
    brutos = scraper.cjsg_download("direito", paginas=range(1, 3))
    df = scraper.cjsg_parse(brutos)
    assert len(brutos) == 2
    assert COLUNAS.issubset(df.columns)
    # 20 resultados por página, sem repetir entre as duas.
    assert len(df) == 40
    assert df["uuid"].is_unique


@pytest.mark.integration
def test_cjsg_filtro_data():
    df = TJTOScraper().cjsg(
        "direito",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="30/06/2024",
        paginas=1,
    )
    assert not df.empty
    assert df["data_julgamento"].dropna().between(date(2024, 1, 1), date(2024, 6, 30)).all()


@pytest.mark.integration
def test_cjsg_tipo_documento_decisoes():
    df = TJTOScraper().cjsg("direito", paginas=1, tipo_documento="decisoes")
    assert not df.empty
