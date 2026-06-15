"""Testes de integracao para o agregador PDPJ.

Bate na API real ``api-processo-integracao.data-lake.pdpj.jus.br``.
Para rodar, defina a variavel de ambiente ``JUSCRAPER_PDPJ_TOKEN`` com
um JWT valido obtido via portal do PDPJ.

Comando: ``pytest tests/pdpj -m integration``.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

import juscraper as jus

pytestmark = pytest.mark.integration

PROCESSOS_DE_TESTE = [
    "10029886420194014100",
    "50211226520184036100",
    "10122143420204013300",
]


def _scraper():
    token = os.environ.get("JUSCRAPER_PDPJ_TOKEN")
    if not token:
        pytest.skip("Defina JUSCRAPER_PDPJ_TOKEN para rodar testes de integracao.")
    s = jus.scraper("pdpj", sleep_time=0.2)
    s.auth(token)
    return s


def test_existe_str_real():
    s = _scraper()
    assert s.existe(PROCESSOS_DE_TESTE[0]) is True


def test_cpopg_real_retorna_detalhes():
    s = _scraper()
    df = s.cpopg(PROCESSOS_DE_TESTE[0])
    assert isinstance(df, pd.DataFrame)
    assert not df.empty
    assert df.iloc[0]["sigla_tribunal"]


def test_documentos_real():
    s = _scraper()
    df = s.documentos(PROCESSOS_DE_TESTE[0])
    assert "id_documento" in df.columns


def test_movimentos_real():
    s = _scraper()
    df = s.movimentos(PROCESSOS_DE_TESTE[0])
    assert "data_hora" in df.columns


def test_partes_real():
    s = _scraper()
    df = s.partes(PROCESSOS_DE_TESTE[0])
    assert "polo" in df.columns


def test_pesquisa_real_por_numero():
    s = _scraper()
    df = s.pesquisa(numero_processo=PROCESSOS_DE_TESTE[0], paginas=1)
    assert not df.empty


def test_contar_real():
    s = _scraper()
    total = s.contar(numero_processo=PROCESSOS_DE_TESTE[0])
    assert isinstance(total, int)
    assert total >= 1


def test_download_documents_real_baixa_texto():
    s = _scraper()
    docs = s.documentos(PROCESSOS_DE_TESTE[1])
    if docs.empty:
        pytest.skip("Processo sem documentos textuais para baixar.")
    out = s.download_documents(docs.head(1), with_text=True)
    assert "texto" in out.columns
    assert out.iloc[0]["texto"]
