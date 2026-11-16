"""Contrato offline do ``auto_chunk`` do TJRO: a busca acima do teto é dividida por data de julgamento.

O portal de mentira responde com os 20 acórdãos reais dos samples
``results_normal_page_0{1,2}.json``, filtrados pelas datas do payload
(``dtjulgamento_inicio``/``dtjulgamento_fim``, limites inclusivos, como medido
ao vivo em 16/11/2026) e paginados por ``from``/``size``. Só o total e o teto
(10 no lugar de 10.000) são do teste.
"""
import json
from datetime import date
from types import SimpleNamespace

import pytest
import requests
import responses

import juscraper as jus
from juscraper.core.exceptions import ColetaParcialError
from juscraper.courts.tjro import download
from tests._helpers import load_sample

TETO = 10

# O aviso da primeira divisão tem teste próprio; nos demais é esperado.
pytestmark = pytest.mark.filterwarnings("ignore:.*Ela será dividida por:UserWarning")


def _hits() -> list[dict]:
    paginas = [json.loads(load_sample("tjro", f"cjsg/results_normal_page_0{n}.json")) for n in (1, 2)]
    return [hit for pagina in paginas for hit in pagina["hits"]["hits"]]


HOJE = "2026-11-16"


@pytest.fixture
def portal(mocker):
    """Registra o portal de mentira e devolve a lista dos payloads recebidos.

    ``portal.falhar`` recebe um predicado do payload: o pedido que o satisfaz cai sem resposta.
    """
    mocker.patch("time.sleep")
    mocker.patch.object(download, "MAX_RESULTS", TETO)
    mocker.patch("juscraper.utils.divisao_por_data._hoje", return_value=date.fromisoformat(HOJE))
    estado = SimpleNamespace(pedidos=[], falhar=None)

    def responder(request):
        payload = json.loads(request.body)
        if estado.falhar and estado.falhar(payload):
            raise requests.ConnectionError("portal caiu")
        estado.pedidos.append(payload)
        if payload["from"] + payload["size"] > TETO:
            return (500, {}, "")
        campos = payload["fields"]
        inicio, fim = campos.get("dtjulgamento_inicio", "0000"), campos.get("dtjulgamento_fim", "9999")
        hits = [hit for hit in _hits() if inicio <= hit["_source"]["dtjulgamento"] <= fim]
        pagina = hits[payload["from"]:payload["from"] + payload["size"]]
        corpo = {"hits": {"total": {"value": len(hits), "relation": "eq"}, "hits": pagina}}
        return (200, {"Content-Type": "application/json"}, json.dumps(corpo))

    with responses.RequestsMock() as rsps:
        rsps.add_callback(responses.POST, download.BASE_URL, callback=responder)
        yield estado


def test_busca_acima_do_teto_e_dividida_por_data_de_julgamento_e_vem_inteira(portal):
    with pytest.warns(UserWarning, match="TJRO: a busca tem 20 resultados.*dividida por data_julgamento") as avisos:
        df = jus.scraper("tjro").cjsg("dano moral")

    assert len(df) == 20
    assert not df.duplicated(subset=["processo", "data_julgamento", "ementa"]).any()
    assert len(avisos) == 1
    # A busca original vai sem data; a divisão vai do piso até hoje, em ISO.
    assert "dtjulgamento_inicio" not in portal.pedidos[0]["fields"]
    assert portal.pedidos[1]["fields"]["dtjulgamento_fim"] == HOJE
    assert min(pedido["fields"]["dtjulgamento_inicio"] for pedido in portal.pedidos[1:]) == "1990-01-01"
    assert all(pedido["fields"]["query"] == "dano moral" for pedido in portal.pedidos)


def test_datas_de_quem_chamou_limitam_a_divisao(portal):
    df = jus.scraper("tjro").cjsg(
        "dano moral", data_julgamento_inicio="01/01/2025", data_julgamento_fim="31/12/2025"
    )

    assert len(df) == 15
    assert all(
        pedido["fields"]["dtjulgamento_inicio"] >= "2025-01-01"
        and pedido["fields"]["dtjulgamento_fim"] <= "2025-12-31"
        for pedido in portal.pedidos
    )


def test_auto_chunk_false_para_no_teto_com_aviso(portal):
    with pytest.warns(UserWarning, match="o portal só entrega as 1 primeiras"):
        df = jus.scraper("tjro").cjsg("dano moral", auto_chunk=False)

    assert len(df) == 10
    assert len(portal.pedidos) == 1


def test_falha_depois_da_divisao_levanta_coleta_parcial_com_dataframe(portal):
    """As janelas mais recentes são baixadas; a mais antiga cai, e o erro leva as primeiras."""
    portal.falhar = lambda payload: (
        payload["fields"]["dtjulgamento_inicio"] == "2024-01-01" and payload["fields"]["dtjulgamento_fim"] < "2026"
    )

    with pytest.raises(ColetaParcialError, match="dividida por data_julgamento") as erro:
        jus.scraper("tjro").cjsg_download(
            "dano moral", data_julgamento_inicio="01/01/2024", data_julgamento_fim="31/12/2026"
        )

    fim_da_janela_que_falhou = date.fromisoformat(erro.value.falhas[0][1])
    assert 0 < len(erro.value.resultado) < 20
    assert {"processo", "data_julgamento", "ementa"} <= set(erro.value.resultado.columns)
    assert erro.value.resultado["data_julgamento"].min() > fim_da_janela_que_falhou
