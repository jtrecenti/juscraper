"""Unit tests for the TRF3 ``cjsg`` parser details the contracts do not pin.

The ``informacoes-basicas`` fragments copy the markup of the first item of
``results_normal_page_01.html``; only the extra span is added by hand.
"""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

import juscraper as jus
from juscraper.courts.trf3.cjsg_parse import _informacoes_basicas
from tests.trf3._cjsg_mock import sample


def _item(*extras: str) -> BeautifulSoup:
    spans = "".join(f'<span class="info">{texto}</span>' for texto in extras)
    html = (
        '<li class="acordao-retorno"><div class="informacoes-basicas">'
        '<span class="info">AI - AGRAVO DE INSTRUMENTO</span>'
        '<span class="info">3ª Turma</span>'
        '<span class="info">\n    Desembargador Federal NERY DA COSTA JUNIOR\n</span>'
        f"{spans}"
        '<span class="info">DJEN DATA: 07/07/2026</span>'
        '<span class="info">Julgamento: 30/06/2026</span>'
        "</div></li>"
    )
    return BeautifulSoup(html, "html.parser").select_one("li")


def test_relator_acordao_reconhecido_pelo_titulo_de_magistrado():
    info = _informacoes_basicas(_item("\n Desembargadora Federal CONSUELO YATSUDA MOROMIZATO YOSHIDA \n"))
    assert info["relator_acordao"] == "Desembargadora Federal CONSUELO YATSUDA MOROMIZATO YOSHIDA"
    assert info["data_publicacao"] == "07/07/2026"
    assert info["data_julgamento"] == "30/06/2026"


@pytest.mark.parametrize("titulo", ["Juíza Federal Convocada", "JUIZ CONVOCADO", "DESEMBARGADOR FEDERAL"])
def test_relator_acordao_aceita_os_titulos_observados(titulo):
    assert _informacoes_basicas(_item(f"{titulo} FULANO"))["relator_acordao"] == f"{titulo} FULANO"


def test_span_sem_rotulo_conhecido_nao_vira_relator_acordao():
    """An unknown span is dropped instead of being taken as the relator para acórdão."""
    info = _informacoes_basicas(_item("Tema 106 do STJ"))
    assert info["relator_acordao"] is None
    assert info["relator"] == "Desembargador Federal NERY DA COSTA JUNIOR"


def test_span_desconhecido_nao_se_junta_ao_relator_acordao():
    info = _informacoes_basicas(_item("Desembargadora Federal CONSUELO YOSHIDA", "Tema 106 do STJ"))
    assert info["relator_acordao"] == "Desembargadora Federal CONSUELO YOSHIDA"


def test_ementa_nao_parte_o_termo_destacado_da_pontuacao():
    """``<em>MEDICAMENTO</em>.`` must stay glued: a ``get_text`` separator would yield ``MEDICAMENTO .``."""
    df = jus.scraper("trf3").cjsg_parse([sample("results_normal_page_01.html").decode("utf-8")])

    ementas = " ".join(df["ementa"])
    assert "FORNECIMENTO DE MEDICAMENTO. ASTREINTES" in ementas
    assert "MEDICAMENTO ." not in ementas
