"""Contratos do teto de ``paginas`` no TJTO: página além do total não vira requisição.

Cada página é uma busca no ``consulta.php``, e o AWS WAF bloqueia o IP depois
de cerca de 7 buscas seguidas. A menor página pedida sai primeiro, e a contagem
dela (a aba ativa, como ``(9)`` em ``single_page.html``) corta as demais.
"""
import logging

import pytest
import responses

import juscraper as jus
from tests._helpers import corpo_form_enviado
from tests.tjto.test_cjsg_contract import _add_post


@pytest.fixture
def tjto(mocker):
    mocker.patch("time.sleep")
    return jus.scraper("tjto")


@pytest.mark.parametrize(("metodo", "instancia", "linhas"), [("cjsg", "2", 9), ("cjpg", "1", 10)])
@responses.activate
def test_paginas_alem_do_total_nao_geram_requisicao(tjto, caplog, metodo, instancia, linhas):
    """``single_page.html`` cabe numa página: as páginas 2 e 3 saem no aviso, sem POST."""
    _add_post('"alimentos avoengos"', start=0, sample_path=f"{metodo}/single_page.html", instancia=instancia)

    with caplog.at_level(logging.WARNING, logger="juscraper.tjto"):
        df = getattr(tjto, metodo)('"alimentos avoengos"', paginas=3)

    assert len(responses.calls) == 1
    assert len(df) == linhas
    assert ("juscraper.tjto", logging.WARNING, "TJTO: páginas 2, 3 fora do intervalo 1-1") in caplog.record_tuples


@responses.activate
def test_a_menor_pagina_pedida_le_o_total_e_corta_as_demais(tjto, caplog):
    """Sem a página 1 pedida, a contagem vem da menor página pedida, sem POST a mais."""
    _add_post("dano moral", start=20, sample_path="cjsg/results_normal_page_02.html")
    _add_post("dano moral", start=40, sample_path="cjsg/results_normal_page_02.html")

    with caplog.at_level(logging.WARNING, logger="juscraper.tjto"):
        brutos = tjto.cjsg_download("dano moral", paginas=[3, 5000, 2, 3])

    # 70.242 resultados em páginas de 20 dão 3.513 páginas; a 2 sai antes, e a 3 só uma vez.
    assert [corpo_form_enviado(call.request)["start"] for call in responses.calls] == ["20", "40"]
    assert len(brutos) == 2
    assert ("juscraper.tjto", logging.WARNING, "TJTO: página 5000 fora do intervalo 1-3513") in caplog.record_tuples


@responses.activate
def test_todas_as_paginas_alem_do_total_custam_uma_requisicao(tjto, caplog):
    """Se a menor página pedida passa do total, as demais também passam: só ela é pedida.

    ``pagina_alem_do_total.html`` é a página 3 real dessa busca (16/11/2026): sem
    linhas, com "Nenhum documento encontrado" e o total da busca, 9, na aba.
    """
    _add_post('"alimentos avoengos"', start=40, sample_path="cjsg/pagina_alem_do_total.html")

    with caplog.at_level(logging.WARNING, logger="juscraper.tjto"):
        df = tjto.cjsg('"alimentos avoengos"', paginas=range(3, 6))

    assert len(responses.calls) == 1
    assert df.empty
    assert ("juscraper.tjto", logging.WARNING, "TJTO: páginas 3, 4, 5 fora do intervalo 1-1") in caplog.record_tuples


@responses.activate
def test_cjpg_sentencas_le_o_total_da_aba_de_sentencas(tjto):
    """``sentencas_page_01.html`` declara 1.284 sentenças e 14 acórdãos: a página 2 é pedida.

    Com o total da aba de acórdãos, a busca caberia numa página e a 2 sairia no aviso.
    A página 2 só precisa ser pedida: o corpo dela repete o da 1.
    """
    for start in (0, 20):
        _add_post('"despejo"', start=start, sample_path="cjpg/sentencas_page_01.html",
                  instancia="1", type_minuta="3")

    df = tjto.cjpg('"despejo"', paginas=range(1, 3), tipo_documento="sentencas")

    assert len(responses.calls) == 2
    assert len(df) == 40
