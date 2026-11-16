"""Testes de integração (rede real) do ComunicaCNJ.

Rodam só com ``pytest -m integration``, de IP residencial: a API responde
HTTP 403 a IPs de datacenter. Medem o limite de data sozinho, que o client
envia sem o outro (``dataDisponibilizacaoInicio`` ou
``dataDisponibilizacaoFim``).
"""
from datetime import date, timedelta

import pytest

import juscraper as jus

pytestmark = pytest.mark.integration

# O sample ``single_page.json`` é desta busca neste dia: 40 comunicações.
_TERMO = "embargos infringentes"
_DIA = "2024-06-03"


@pytest.fixture
def comunica():
    return jus.scraper("comunica_cnj", verbose=0, sleep_time=1.0)


def test_so_o_limite_superior_e_respeitado(comunica):
    """Se a API ignorasse o limite, a primeira página traria comunicações recentes."""
    df = comunica.listar_comunicacoes(_TERMO, paginas=1, data_disponibilizacao_fim=_DIA)

    assert len(df) > 0
    assert (df["data_disponibilizacao"] <= _DIA).all()


def test_so_o_limite_inferior_e_aceito(comunica):
    """Só confere que a API aceita o limite: a primeira página já vem das mais recentes."""
    inicio = (date.today() - timedelta(days=7)).isoformat()

    df = comunica.listar_comunicacoes(_TERMO, paginas=1, data_disponibilizacao_inicio=inicio)

    assert len(df) > 0
    assert (df["data_disponibilizacao"] >= inicio).all()

