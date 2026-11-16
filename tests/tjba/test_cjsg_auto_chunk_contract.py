"""Contrato offline do ``auto_chunk`` do TJBA: a busca acima do teto é dividida por data de publicação.

O portal de mentira responde com as 20 decisões reais dos samples
``results_normal_page_0{1,2}.json`` (19 publicadas em 29/12/2025 e 1 em
30/12/2025), filtradas por ``dataInicial``/``dataFinal`` (limites inclusivos,
como medido ao vivo em 16/11/2026) e paginadas. Só as contagens e o teto (15
no lugar de 10.000) são do teste. O dia 29 sozinho passa desse teto.
"""
import json
from datetime import date
from types import SimpleNamespace

import pytest
import requests
import responses

import juscraper as jus
from juscraper.core.exceptions import ColetaParcialError
from juscraper.courts.tjba import download
from tests._helpers import load_sample

TETO = 15
POR_PAGINA = 5


def _decisoes() -> list[dict]:
    paginas = [json.loads(load_sample("tjba", f"cjsg/results_normal_page_0{n}.json")) for n in (1, 2)]
    decisoes = [decisao for pagina in paginas for decisao in pagina["data"]["filter"]["decisoes"]]
    return sorted(decisoes, key=lambda decisao: decisao["dataPublicacao"], reverse=True)


HOJE = "2026-11-16"


@pytest.fixture
def portal(mocker):
    """Registra o portal de mentira e devolve a lista das variáveis GraphQL recebidas.

    ``portal.falhar`` recebe um predicado do ``decisaoFilter``: o pedido que o satisfaz cai sem resposta.
    """
    mocker.patch("time.sleep")
    mocker.patch.object(download, "MAX_RESULTS", TETO)
    mocker.patch("juscraper.utils.divisao_por_data._hoje", return_value=date.fromisoformat(HOJE))
    estado = SimpleNamespace(pedidos=[], falhar=None)

    def responder(request):
        variaveis = json.loads(request.body)["variables"]
        if estado.falhar and estado.falhar(variaveis["decisaoFilter"]):
            raise requests.ConnectionError("portal caiu")
        estado.pedidos.append(variaveis)
        if (variaveis["pageNumber"] + 1) * variaveis["itemsPerPage"] > TETO:
            return (200, {}, json.dumps({"data": None, "errors": [{"message": "Internal Server Error(s)"}]}))
        filtro = variaveis["decisaoFilter"]
        inicio, fim = filtro["dataInicial"][:10], filtro.get("dataFinal", "9999")[:10]
        decisoes = [d for d in _decisoes() if inicio <= d["dataPublicacao"][:10] <= fim]
        corte = variaveis["pageNumber"] * variaveis["itemsPerPage"]
        corpo = {"data": {"filter": {
            "decisoes": decisoes[corte:corte + variaveis["itemsPerPage"]],
            "pageCount": -(-len(decisoes) // variaveis["itemsPerPage"]),
            "itemCount": len(decisoes),
        }}}
        return (200, {"Content-Type": "application/json"}, json.dumps(corpo))

    with responses.RequestsMock() as rsps:
        rsps.add_callback(responses.POST, download.GRAPHQL_URL, callback=responder)
        yield estado


def test_busca_acima_do_teto_e_dividida_por_data_de_publicacao(portal):
    with pytest.warns(UserWarning, match=r"o dia 2025-12-29 tem 19 resultados.*só entrega os 15 primeiros") as avisos:
        df = jus.scraper("tjba").cjsg("dano moral", tamanho_pagina=POR_PAGINA)

    assert len([aviso for aviso in avisos if issubclass(aviso.category, UserWarning)]) == 1
    # O dia 30 inteiro (1 decisão) e as 15 primeiras do dia 29, da janela mais recente para a mais antiga.
    assert len(df) == 16
    assert df["data_publicacao"].is_monotonic_decreasing
    # A busca original vai como sempre foi; a divisão manda as duas datas no formato do portal.
    assert "dataFinal" not in portal.pedidos[0]["decisaoFilter"]
    assert portal.pedidos[1]["decisaoFilter"]["dataInicial"] == "1980-02-01T03:00:00.000Z"
    assert portal.pedidos[1]["decisaoFilter"]["dataFinal"] == f"{HOJE}T03:00:00.000Z"
    assert all(pedido["decisaoFilter"]["assunto"] == "dano moral" for pedido in portal.pedidos)


@pytest.mark.usefixtures("portal")
def test_decisao_que_o_portal_repete_na_mesma_janela_fica_como_veio():
    """O sample traz a mesma decisão (``hash`` igual) duas vezes, com órgãos julgadores diferentes."""
    repetidos = [d["hash"] for d in _decisoes()]
    assert len(set(repetidos)) == 19

    with pytest.warns(UserWarning, match="só entrega os 15 primeiros"):
        brutos = jus.scraper("tjba").cjsg_download("dano moral", tamanho_pagina=POR_PAGINA)

    baixados = [d["hash"] for pagina in brutos for d in pagina["data"]["filter"]["decisoes"]]
    assert baixados == [d["hash"] for d in _decisoes() if d["dataPublicacao"] > "2025-12-30"] + [
        d["hash"] for d in _decisoes() if d["dataPublicacao"] < "2025-12-30"
    ][:TETO]


def test_auto_chunk_false_para_no_teto_com_aviso(portal):
    with pytest.warns(UserWarning, match="o portal só entrega as 3 primeiras"):
        df = jus.scraper("tjba").cjsg("dano moral", tamanho_pagina=POR_PAGINA, auto_chunk=False)

    assert len(df) == 15
    assert len(portal.pedidos) == 3


def test_falha_depois_da_divisao_levanta_coleta_parcial_com_dataframe(portal):
    portal.falhar = lambda filtro: filtro["dataInicial"][:10] == filtro.get("dataFinal", "")[:10] == "2025-12-29"

    with pytest.raises(ColetaParcialError, match="Falta o intervalo que termina em 2025-12-29") as erro:
        jus.scraper("tjba").cjsg_download("dano moral", tamanho_pagina=POR_PAGINA)

    assert len(erro.value.resultado) == 1
    assert {"processo", "data_publicacao", "hash"} <= set(erro.value.resultado.columns)
