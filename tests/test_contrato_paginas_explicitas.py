"""``paginas`` explícito no ``cjsg``: página repetida uma vez só e página além do total sem pedido.

Contrato comum dos portais JSON (TJRN e TJRO, Elasticsearch, total em
``hits.total``; TJPA, ``data.totalPages``; TJBA, GraphQL, ``pageCount``; TJES,
``total_pages``; TJPB, ``total``) e dos HTML (TJSC, total no cabeçalho de toda
página; TJPI, contagem "de um total de N"), como já valia para TJGO,
TJMG, TJRJ, TJTO e o eSAJ. A menor página pedida sai primeiro, porque é dela
que vem o total (como no TJTO); as demais saem na ordem pedida. Os samples são
respostas reais: a busca "dano moral" tem 69.440 resultados no TJRN e 23.109
no TJSC, 10 por página, e 400 páginas no TJPA. Os ``alem_do_total`` de TJBA e
TJRO são a resposta a uma página além do total (65 e 72 páginas) e dentro do
teto de 10.000 resultados desses portais, que tem os contratos no fim do
arquivo.
"""
from __future__ import annotations

import json
import logging
from typing import cast
from urllib.parse import parse_qs, urlparse

import pytest
import responses

import juscraper as jus
from juscraper.courts.tjba import download as tjba_download
from juscraper.courts.tjes import download as tjes_download
from juscraper.courts.tjpa import download as tjpa_download
from juscraper.courts.tjpb import download as tjpb_download
from juscraper.courts.tjpi import download as tjpi_download
from juscraper.courts.tjro import download as tjro_download
from juscraper.courts.tjsc.download import AJAX_URL, SEARCH_URL
from tests._helpers import load_sample, load_sample_bytes
from tests.tjpb._helpers import add_get_classes


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


URLS = {
    "tjba": tjba_download.GRAPHQL_URL,
    "tjpa": tjpa_download.BASE_URL,
    "tjro": tjro_download.BASE_URL,
}
MODULOS_COM_TETO = {"tjba": tjba_download, "tjro": tjro_download}


def _registrar_json(tribunal: str, sample: str):
    def registrar() -> None:
        responses.add(
            responses.POST, URLS[tribunal], body=load_sample(tribunal, f"cjsg/{sample}.json"),
            content_type="application/json",
        )
    return registrar


def _pagina_tjba(request) -> int:
    return cast("int", json.loads(request.body)["variables"]["pageNumber"]) + 1


def _pagina_tjpa(request) -> int:
    return cast("int", json.loads(request.body)["page"]) + 1


def _pagina_tjro(request) -> int:
    return cast("int", json.loads(request.body)["from"]) // tjro_download.RESULTS_PER_PAGE + 1


# TJES (GET, JSON), TJPB (POST, JSON, depois do GET do token) e TJPI (GET,
# HTML): método, URL, extensão do sample e tipo da resposta da busca.
BUSCAS = {
    "tjes": (responses.GET, f"{tjes_download.BASE_URL}/search", "json", "application/json"),
    "tjpb": (responses.POST, tjpb_download.SEARCH_URL, "json", "application/json"),
    "tjpi": (responses.GET, tjpi_download.BASE_URL, "html", "text/html; charset=utf-8"),
}


def _registrar_busca(tribunal: str, corpo_de=None):
    """Registra a busca do portal; ``corpo_de(pagina)`` escolhe o corpo, e o default é a página 2."""
    def registrar() -> None:
        metodo, url, extensao, tipo = BUSCAS[tribunal]
        pagina_2 = load_sample(tribunal, f"cjsg/results_normal_page_02.{extensao}")
        if tribunal == "tjpb":
            add_get_classes()
        responses.add_callback(
            metodo,
            url,
            callback=lambda request: (
                200, {}, corpo_de(PORTAIS[tribunal][1](request)) if corpo_de else pagina_2,
            ),
            content_type=tipo,
        )
    return registrar


def _pagina_da_query(request) -> int:
    return int(parse_qs(urlparse(request.url).query)["page"][0])


def _pagina_tjpb(request) -> int | None:
    return cast("int", json.loads(request.body)["page"]) if request.method == "POST" else None


# Por portal: registro das respostas, leitura da página pedida e uma página
# além do total da busca do sample (no TJBA e no TJRO, a do próprio sample).
PORTAIS = {
    "tjba": (_registrar_json("tjba", "alem_do_total"), _pagina_tjba, 901),
    "tjes": (_registrar_busca("tjes"), _pagina_da_query, 10**6),
    "tjpa": (_registrar_json("tjpa", "results_normal_page_02"), _pagina_tjpa, 10**6),
    "tjpb": (_registrar_busca("tjpb"), _pagina_tjpb, 10**6),
    "tjpi": (_registrar_busca("tjpi"), _pagina_da_query, 10**6),
    "tjrn": (_registrar_tjrn, _pagina_tjrn, 10**6),
    "tjro": (_registrar_json("tjro", "alem_do_total"), _pagina_tjro, 501),
    "tjsc": (_registrar_tjsc, _pagina_tjsc, 10**6),
}


def _paginas_pedidas(tribunal: str) -> list[int]:
    """As páginas das buscas, na ordem dos pedidos; o GET do token do TJPB fica de fora."""
    paginas = (PORTAIS[tribunal][1](chamada.request) for chamada in responses.calls)
    return [pagina for pagina in paginas if pagina is not None]


@pytest.mark.parametrize("tribunal", list(PORTAIS))
@responses.activate
def test_repetida_e_alem_do_total_sem_pedido(tribunal, mocker, caplog):
    mocker.patch("time.sleep")
    registrar, _, alem = PORTAIS[tribunal]
    registrar()

    with caplog.at_level(logging.WARNING, logger=f"juscraper.{tribunal}"):
        brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[3, 2, 3, alem])

    assert _paginas_pedidas(tribunal) == [2, 3]
    assert len(brutos) == 2
    assert f"{tribunal.upper()}: página {alem} fora do intervalo" in caplog.text


@pytest.mark.parametrize("tribunal", list(PORTAIS))
@responses.activate
def test_so_paginas_alem_do_total_pede_so_a_menor(tribunal, mocker):
    """Só a menor página é pedida, para ler o total; nenhuma linha volta."""
    mocker.patch("time.sleep")
    registrar, _, alem = PORTAIS[tribunal]
    registrar()

    brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[alem, alem + 1])

    assert _paginas_pedidas(tribunal) == [alem]
    assert brutos == []


@pytest.mark.parametrize("tribunal", list(URLS))
@responses.activate
def test_menor_pagina_volta_na_posicao_pedida(tribunal, mocker):
    """A menor página é pedida antes das outras, mas o retorno segue a ordem de ``paginas``."""
    mocker.patch("time.sleep")
    pagina_de = PORTAIS[tribunal][1]
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


@pytest.mark.parametrize("tribunal", list(BUSCAS))
@responses.activate
def test_menor_pagina_volta_na_posicao_pedida_tjes_tjpb_tjpi(tribunal, mocker):
    mocker.patch("time.sleep")
    extensao = BUSCAS[tribunal][2]
    pagina_2 = load_sample(tribunal, f"cjsg/results_normal_page_02.{extensao}")
    outra = load_sample(tribunal, f"cjsg/results_normal_page_01.{extensao}")
    _registrar_busca(tribunal, lambda pagina: pagina_2 if pagina == 2 else outra)()

    brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[5, 2, 4])

    esperado = [outra, pagina_2, outra]
    assert _paginas_pedidas(tribunal) == [2, 5, 4]
    assert brutos == (esperado if extensao == "html" else [json.loads(corpo) for corpo in esperado])


@responses.activate
def test_tjes_cjpg_segue_o_mesmo_contrato(mocker, caplog):
    """O ``cjpg`` do TJES usa o download do ``cjsg``, com ``core=pje1g``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.GET, BUSCAS["tjes"][1], body=load_sample("tjes", "cjpg/results_normal_page_02.json"),
        content_type="application/json",
    )

    with caplog.at_level(logging.WARNING, logger="juscraper.tjes"):
        brutos = jus.scraper("tjes").cjpg_download("dano moral", paginas=[3, 2, 3, 10**6])

    assert _paginas_pedidas("tjes") == [2, 3]
    assert len(brutos) == 2
    assert "TJES: página 1000000 fora do intervalo" in caplog.text


@pytest.mark.parametrize("tribunal", list(MODULOS_COM_TETO))
@pytest.mark.parametrize("paginas", [[1, 1001], range(1, 10**7), 1001])
@responses.activate
def test_pagina_alem_do_teto_levanta_sem_pedido(tribunal, paginas):
    """TJBA e TJRO respondem com erro além dos 10.000 resultados; a página não chega a ser pedida."""
    with pytest.raises(ValueError, match=r"só entrega as 1000 primeiras páginas"):
        jus.scraper(tribunal).cjsg_download("dano moral", paginas=paginas)

    assert len(responses.calls) == 0


@pytest.mark.parametrize("tribunal", list(MODULOS_COM_TETO))
@responses.activate
def test_todas_as_paginas_param_no_teto_com_aviso(tribunal, mocker):
    """``paginas=None`` numa busca acima do teto baixa até ele e avisa; o teto é reduzido para o teste."""
    mocker.patch("time.sleep")
    mocker.patch.object(MODULOS_COM_TETO[tribunal], "MAX_RESULTS", 30)
    _registrar_json(tribunal, "results_normal_page_02")()

    with pytest.warns(UserWarning, match=r"só entrega as 3 primeiras"):
        brutos = jus.scraper(tribunal).cjsg_download("dano moral")

    assert _paginas_pedidas(tribunal) == [1, 2, 3]
    assert len(brutos) == 3


@pytest.mark.parametrize("tribunal", list(MODULOS_COM_TETO))
@responses.activate
def test_ultima_pagina_do_teto_e_pedida(tribunal, mocker):
    mocker.patch("time.sleep")
    _registrar_json(tribunal, "results_normal_page_02")()

    brutos = jus.scraper(tribunal).cjsg_download("dano moral", paginas=[1000])

    assert _paginas_pedidas(tribunal) == [1000]
    assert len(brutos) == 1
