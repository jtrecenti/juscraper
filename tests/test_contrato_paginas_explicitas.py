"""``paginas`` explícito no ``cjsg``: página repetida uma vez só e página além do total sem pedido.

Contrato comum dos portais JSON (TJRN e TJRO, Elasticsearch, total em
``hits.total``; TJPA, ``data.totalPages``; TJBA, GraphQL, ``pageCount``) e de
um HTML (TJSC, total no cabeçalho de toda página), como já valia para TJGO,
TJMG, TJRJ, TJTO e o eSAJ. A menor página pedida sai primeiro, porque é dela
que vem o total (como no TJTO); as demais saem na ordem pedida. Os samples são
respostas reais: a busca "dano moral" tem 69.440 resultados no TJRN e 23.109
no TJSC, 10 por página; os de TJBA, TJPA e TJRO são de página 2, com 121.786,
400 e 11.635 páginas.
"""
from __future__ import annotations

import json
import logging
from typing import cast
from urllib.parse import parse_qs

import pytest
import responses

import juscraper as jus
from juscraper.courts.tjsc.download import AJAX_URL, SEARCH_URL
from tests._helpers import load_sample, load_sample_bytes


def _registrar_tjrn() -> None:
    responses.add_callback(
        responses.POST,
        "https://jurisprudencia.tjrn.jus.br/api/pesquisar",
        callback=lambda _request: (200, {}, load_sample("tjrn", "cjsg/results_normal_page_01.json")),
        content_type="application/json",
    )


def _pagina_tjrn(request) -> int:
    return cast("int", json.loads(request.body)["page"])


def _registrar_tjsc() -> None:
    corpo = load_sample_bytes("tjsc", "cjsg/results_normal_page_02.html")
    for url in (SEARCH_URL, AJAX_URL):
        responses.add_callback(
            responses.POST, url, callback=lambda _request: (200, {}, corpo),
            content_type="text/html; charset=iso-8859-1",
        )


def _pagina_tjsc(request) -> int:
    return int(parse_qs(request.body)["hdnPaginaAtual"][0])


def _registrar_json(tribunal: str):
    def registrar() -> None:
        responses.add(
            responses.POST, URLS[tribunal], body=load_sample(tribunal, "cjsg/results_normal_page_02.json"),
            content_type="application/json",
        )
    return registrar


def _pagina_tjba(request) -> int:
    return cast("int", json.loads(request.body)["variables"]["pageNumber"]) + 1


def _pagina_tjpa(request) -> int:
    return cast("int", json.loads(request.body)["page"]) + 1


def _pagina_tjro(request) -> int:
    return cast("int", json.loads(request.body)["from"]) // 10 + 1


URLS = {
    "tjba": "https://jurisprudenciaws.tjba.jus.br/graphql",
    "tjpa": "https://jurisprudencia.tjpa.jus.br/bff/api/decisoes/buscar",
    "tjro": "https://juris-back.tjro.jus.br/search/varios_parametros/",
}

PORTAIS = {
    "tjba": (_registrar_json("tjba"), _pagina_tjba),
    "tjpa": (_registrar_json("tjpa"), _pagina_tjpa),
    "tjrn": (_registrar_tjrn, _pagina_tjrn),
    "tjro": (_registrar_json("tjro"), _pagina_tjro),
    "tjsc": (_registrar_tjsc, _pagina_tjsc),
}


def _paginas_pedidas(tribunal: str) -> list[int]:
    return [PORTAIS[tribunal][1](chamada.request) for chamada in responses.calls]


@pytest.mark.parametrize("tribunal", list(PORTAIS))
@responses.activate
def test_repetida_e_alem_do_total_sem_pedido(tribunal, mocker, caplog):
    mocker.patch("time.sleep")
    PORTAIS[tribunal][0]()

    with caplog.at_level(logging.WARNING, logger=f"juscraper.{tribunal}"):
        brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[3, 2, 3, 10**6])

    assert _paginas_pedidas(tribunal) == [2, 3]
    assert len(brutos) == 2
    assert f"{tribunal.upper()}: página 1000000 fora do intervalo" in caplog.text


@pytest.mark.parametrize("tribunal", list(PORTAIS))
@responses.activate
def test_so_paginas_alem_do_total_pede_so_a_menor(tribunal, mocker):
    """Só a menor página é pedida, para ler o total; nenhuma linha volta."""
    mocker.patch("time.sleep")
    PORTAIS[tribunal][0]()

    brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[10**6, 10**6 + 1])

    assert _paginas_pedidas(tribunal) == [10**6]
    assert brutos == []


@pytest.mark.parametrize("tribunal", ["tjba", "tjpa", "tjro"])
@responses.activate
def test_menor_pagina_volta_na_posicao_pedida(tribunal, mocker):
    """A menor página é pedida antes das outras, mas o retorno segue a ordem de ``paginas``."""
    mocker.patch("time.sleep")
    _, pagina_de = PORTAIS[tribunal]
    pagina_2 = load_sample(tribunal, "cjsg/results_normal_page_02.json")
    outra = load_sample(tribunal, "cjsg/results_normal_page_01.json")
    responses.add_callback(
        responses.POST,
        URLS[tribunal],
        callback=lambda request: (200, {}, pagina_2 if pagina_de(request) == 2 else outra),
        content_type="application/json",
    )

    brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[5, 2, 4])

    assert _paginas_pedidas(tribunal) == [2, 5, 4]
    assert brutos == [json.loads(outra), json.loads(pagina_2), json.loads(outra)]
