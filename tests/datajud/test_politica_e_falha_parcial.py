"""Timeout pelo perfil HTTP ``"busca"`` e aviso de paginação interrompida no DataJud."""

from __future__ import annotations

from typing import Any

import pytest
import responses

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client

URL_TJSP = "https://api-publica.datajud.cnj.jus.br/api_publica_tjsp/_search"
RESPOSTA_VAZIA = {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}


def _pagina(pagina: int, *, tamanho: int = 10, total: int = 25, relation: str = "eq") -> dict[str, Any]:
    hits = [
        {
            "_source": {"numeroProcesso": f"{pagina:02d}-{item:02d}"},
            "sort": [f"cursor-{pagina:02d}-{item:02d}"],
        }
        for item in range(tamanho)
    ]
    return {"hits": {"total": {"value": total, "relation": relation}, "hits": hits}}


def _instalar_paginas(monkeypatch, paginas: list[dict[str, Any] | None]) -> None:
    respostas = iter(paginas)
    monkeypatch.setattr(datajud_client, "call_datajud_api", lambda **_: next(respostas))
    monkeypatch.setattr(datajud_client.time, "sleep", lambda _: None)


# ---------------------------------------------------------------------------
# politica= e timeout
# ---------------------------------------------------------------------------


@responses.activate
@pytest.mark.parametrize("politica, esperado", [(None, 60), ({"busca": {"timeout": 180}}, 180)])
def test_timeout_do_perfil_chega_ao_listar_processos(mocker, politica, esperado):
    scraper = jus.scraper("datajud", verbose=0, politica=politica)
    espiao = mocker.spy(scraper.session, "post")
    responses.add(responses.POST, URL_TJSP, json=RESPOSTA_VAZIA)

    scraper.listar_processos(tribunal="TJSP")

    assert espiao.call_args.kwargs["timeout"] == esperado


@responses.activate
@pytest.mark.parametrize("politica, esperado", [(None, 60), ({"busca": {"timeout": 180}}, 180)])
def test_timeout_do_perfil_chega_ao_contar_processos(mocker, politica, esperado):
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0, politica=politica)
    espiao = mocker.spy(scraper.session, "post")
    responses.add(responses.POST, URL_TJSP, json=RESPOSTA_VAZIA)

    scraper.contar_processos(tribunal="TJSP")

    assert espiao.call_args.kwargs["timeout"] == esperado


@responses.activate
def test_timeout_do_perfil_vale_tambem_no_retry_com_size_reduzido(mocker):
    scraper = jus.scraper("datajud", verbose=0, politica={"busca": {"timeout": 180}})
    espiao = mocker.spy(scraper.session, "post")
    responses.add(responses.POST, URL_TJSP, status=504)
    responses.add(responses.POST, URL_TJSP, json=RESPOSTA_VAZIA)

    with pytest.warns(UserWarning, match="Refazendo com"):
        scraper.listar_processos(tribunal="TJSP")

    assert [chamada.kwargs["timeout"] for chamada in espiao.call_args_list] == [180, 180]


def test_politica_com_campo_sem_efeito_no_datajud_levanta():
    with pytest.raises(ValueError, match=r"só aceita \['timeout'\].*max_retries"):
        jus.scraper("datajud", politica={"busca": {"timeout": 90, "max_retries": 5}})


def test_politica_com_perfil_desconhecido_levanta():
    with pytest.raises(ValueError, match="Perfil HTTP desconhecido"):
        jus.scraper("datajud", politica={"listagem": {"timeout": 90}})


# ---------------------------------------------------------------------------
# Aviso de paginação interrompida
# ---------------------------------------------------------------------------


def test_falha_na_primeira_pagina_avisa_que_nada_veio_e_sugere_saida(monkeypatch):
    _instalar_paginas(monkeypatch, [None])

    with pytest.warns(UserWarning) as avisos:
        df = jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP")

    mensagem = str(avisos[0].message)
    assert "página 1. Resultados parciais retornados: nenhum registro recebido" in mensagem
    assert "data_ajuizamento_inicio" in mensagem
    assert "politica={'busca': {'timeout'" in mensagem
    assert df.empty


def test_falha_no_meio_diz_quanto_veio_de_quanto_foi_encontrado(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2), None])

    with pytest.warns(UserWarning) as avisos:
        df = jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    mensagem = str(avisos[0].message)
    assert "página 3. Resultados parciais retornados: 20 registro(s) recebido(s) de 25" in mensagem
    assert len(df) == 20


def test_total_truncado_pelo_elasticsearch_vira_pelo_menos(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1, total=10000, relation="gte"), None])

    with pytest.warns(UserWarning, match="10 registro\\(s\\) recebido\\(s\\) de pelo menos 10000"):
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)


def test_paginas_descartadas_antes_do_intervalo_nao_contam_como_recebidas(monkeypatch):
    # Com ``paginas=range(2, 4)`` a página 1 é percorrida pelo cursor e
    # descartada; ela não está no DataFrame, então não entra na contagem.
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2), None])

    with pytest.warns(UserWarning) as avisos:
        df = jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP", tamanho_pagina=10, paginas=range(2, 4)
        )

    assert "10 registro(s) recebido(s) de 25" in str(avisos[0].message)
    assert len(df) == 10
