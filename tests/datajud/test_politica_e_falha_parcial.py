"""Timeout pelo perfil HTTP ``"busca"`` e aviso de paginação interrompida no DataJud."""

from __future__ import annotations

import json
import warnings
from typing import Any

import pytest
import responses

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import ColetaParcialError
from tests._helpers import load_sample

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


@responses.activate
def test_json_malformado_apos_pagina_valida_nao_devolve_resultado_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1), status=200)
    responses.add(
        responses.POST,
        URL_TJSP,
        body="{json malformado",
        content_type="application/json",
        status=200,
    )

    # O comportamento atual emite um aviso antes de devolver o parcial. O
    # teste isola o contrato desejado: falha explícita com os dados recebidos.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]


@responses.activate
def test_resposta_estruturalmente_malformada_apos_pagina_valida_preserva_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    sample_body = load_sample("datajud", "listar_processos/results_normal_page_01.json")
    sample = json.loads(sample_body)
    processos_sample = [hit["_source"]["numeroProcesso"] for hit in sample["hits"]["hits"]]
    responses.add(
        responses.POST,
        URL_TJSP,
        body=sample_body,
        content_type="application/json",
        status=200,
    )
    responses.add(
        responses.POST,
        URL_TJSP,
        json={"hits": {"hits": ["not-a-dict"]}},
        status=200,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == processos_sample


@responses.activate
def test_hits_null_apos_pagina_valida_gera_erro_com_resultado_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1), status=200)
    responses.add(
        responses.POST,
        URL_TJSP,
        json={"hits": {"hits": None}},
        status=200,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]


@responses.activate
def test_hits_none_apos_pagina_valida_preserva_resultado_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=25), status=200)
    responses.add(responses.POST, URL_TJSP, json={"hits": None}, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_hits_total_string_na_primeira_pagina_gera_erro_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    pagina1 = _pagina(1, total=25)
    pagina1["hits"]["total"] = "25"
    responses.add(responses.POST, URL_TJSP, json=pagina1, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert erro.resultado.empty
    assert "api_publica_tjsp" in str(erro)
    assert "página 1" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_hits_hits_string_apos_pagina_valida_preserva_resultado_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    pagina2 = _pagina(2, total=25)
    pagina2["hits"]["hits"] = "0123456789abcdef"
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=25), status=200)
    responses.add(responses.POST, URL_TJSP, json=pagina2, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(1, 3),
            tamanho_pagina=10,
        )

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_hit_final_sem_dict_apos_pagina_valida_preserva_resultado_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    pagina2 = _pagina(2, total=25)
    pagina2["hits"]["hits"][-1] = "not-a-dict"
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=25), status=200)
    responses.add(responses.POST, URL_TJSP, json=pagina2, status=200)

    try:
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(
                tribunal="TJSP",
                paginas=range(1, 3),
                tamanho_pagina=10,
            )
    finally:
        assert len(responses.calls) == 2

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_pagina_intermediaria_com_hits_null_gera_erro_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    pagina1 = _pagina(1, total=25)
    pagina1["hits"]["hits"] = None
    responses.add(responses.POST, URL_TJSP, json=pagina1, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(2, 3),
            tamanho_pagina=10,
        )

    erro = exc_info.value
    assert erro.resultado.empty
    assert "api_publica_tjsp" in str(erro)
    assert "página 1" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_pagina_vazia_antes_do_total_exato_gera_erro_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=25), status=200)
    responses.add(
        responses.POST,
        URL_TJSP,
        json={"hits": {"total": {"value": 25, "relation": "eq"}, "hits": []}},
        status=200,
    )

    try:
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)
    finally:
        assert len(responses.calls) == 2

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert "10 registro(s) recebido(s) de 25 encontrado(s)" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_pagina_curta_antes_do_total_exato_gera_erro_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=25), status=200)
    responses.add(responses.POST, URL_TJSP, json=_pagina(2, tamanho=1, total=25), status=200)

    try:
        with pytest.raises(ColetaParcialError) as exc_info:
            scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)
    finally:
        assert len(responses.calls) == 2

    erro = exc_info.value
    assert len(erro.resultado) == 11
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ] + ["02-00"]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert "11 registro(s) recebido(s) de 25 encontrado(s)" in str(erro)
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_cursor_search_after_ausente_com_pagina_pendente_gera_erro_parcial():
    pagina = _pagina(1)
    del pagina["hits"]["hits"][-1]["sort"]
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=pagina, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(1, 3),
            tamanho_pagina=10,
        )

    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]


@responses.activate
def test_falha_em_um_alias_nao_impede_consulta_dos_demais():
    cnj_tjac = "00033258820148010001"
    cnj_tjsp = "01234567820238260001"
    url_tjac = "https://api-publica.datajud.cnj.jus.br/api_publica_tjac/_search"
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, url_tjac, status=500)
    responses.add(responses.POST, URL_TJSP, json=_pagina(2, tamanho=1, total=1), status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            numero_processo=[cnj_tjac, cnj_tjsp],
            paginas=1,
            tamanho_pagina=10,
        )

    urls_chamadas = [call.request.url for call in responses.calls]
    assert urls_chamadas == [url_tjac, URL_TJSP]
    assert len(exc_info.value.resultado) == 1
    assert exc_info.value.resultado["numeroProcesso"].tolist() == ["02-00"]
    assert "api_publica_tjac" in str(exc_info.value.falhas[0][2])


@responses.activate
def test_campo_hits_hits_ausente_apos_pagina_valida_gera_erro_parcial():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1), status=200)
    responses.add(responses.POST, URL_TJSP, json={"hits": {}}, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(1, 3),
            tamanho_pagina=10,
        )

    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]


@responses.activate
@pytest.mark.parametrize(
    "resposta",
    [
        pytest.param({}, id="hits-ausente"),
        pytest.param({"hits": "not-an-object"}, id="hits-nao-objeto"),
        pytest.param({"hits": {}}, id="hits-hits-ausente"),
    ],
)
def test_envelope_invalido_na_pagina_de_navegacao_gera_erro_parcial(resposta):
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=resposta, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(2, 3),
            tamanho_pagina=10,
        )

    erro = exc_info.value
    assert erro.resultado.empty
    assert "api_publica_tjsp" in str(erro)
    assert "página 1" in str(erro)
    assert len(responses.calls) == 1
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_hit_com_source_vazio_nao_encerra_coleta_silenciosamente():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    pagina2 = _pagina(2, tamanho=1, total=11)
    pagina2["hits"]["hits"][0]["_source"] = {}
    responses.add(responses.POST, URL_TJSP, json=_pagina(1, total=11), status=200)
    responses.add(responses.POST, URL_TJSP, json=pagina2, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in str(erro)
    assert "página 2" in str(erro)
    assert len(responses.calls) == 2
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


@responses.activate
def test_hit_sem_source_apos_pagina_valida_gera_erro_preservando_parcial():
    pagina2 = _pagina(2)
    del pagina2["hits"]["hits"][4]["_source"]
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(responses.POST, URL_TJSP, json=_pagina(1), status=200)
    responses.add(responses.POST, URL_TJSP, json=pagina2, status=200)

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(1, 3),
            tamanho_pagina=10,
        )

    assert len(responses.calls) == 2
    assert len(exc_info.value.resultado) == 10
    assert exc_info.value.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]


@responses.activate
def test_erro_parcial_informa_alias_pagina_total_e_causa():
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)
    responses.add(
        responses.POST,
        URL_TJSP,
        json=_pagina(1, total=37),
        status=200,
    )
    responses.add(
        responses.POST,
        URL_TJSP,
        json={"hits": {"hits": ["not-a-dict"]}},
        status=200,
    )

    with pytest.raises(ColetaParcialError) as exc_info:
        scraper.listar_processos(
            tribunal="TJSP",
            paginas=range(1, 3),
            tamanho_pagina=10,
        )

    erro = exc_info.value
    mensagem = str(erro)
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert "api_publica_tjsp" in mensagem
    assert "página 2" in mensagem
    assert "10 registro(s) recebido(s) de 37 encontrado(s)" in mensagem
    assert erro.falhas
    causas = [falha[2] for falha in erro.falhas if isinstance(falha[2], Exception)]
    assert causas
    assert any(erro.__cause__ is causa for causa in causas)


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


@pytest.mark.parametrize(
    "ajuste",
    [
        {"timeout": 90, "max_retries": 5},
        # Inválidos para a ``RequestPolicy`` (TypeError e ValueError do core):
        # o DataJud recusa antes, com a mesma explicação dos demais campos.
        {"retryable_statuses": 500},
        {"max_retries": 0},
        {"campo_inexistente": 1},
    ],
)
def test_politica_com_campo_sem_efeito_no_datajud_levanta(ajuste):
    with pytest.raises(ValueError, match=r"só aceita \['timeout'\]"):
        jus.scraper("datajud", politica={"busca": ajuste})


@pytest.mark.parametrize(
    "timeout",
    # ``inf`` é positivo, mas o ``requests`` levanta ``OverflowError`` ao usá-lo.
    # ``10**400`` não cabe em ``float``: sem tratamento, a própria validação
    # levantaria ``OverflowError`` em vez de ``ValueError``.
    [
        "abc", -1, 0, True, None, [5], [5, -1], (5, "x"),
        float("inf"), float("nan"), (5, float("inf")),
        pytest.param(10**400, id="10**400"),
        pytest.param(-10**400, id="-10**400"),
        pytest.param((5, 10**400), id="par-com-10**400"),
    ],
)
def test_politica_com_timeout_invalido_levanta(timeout):
    with pytest.raises(ValueError, match="timeout inválido"):
        jus.scraper("datajud", politica={"busca": {"timeout": timeout}})


@pytest.mark.parametrize("timeout, esperado", [(90, 90), (12.5, 12.5), ([5, 180], (5, 180)), ((5, 180), (5, 180))])
def test_politica_com_timeout_valido_e_aceita(timeout, esperado):
    scraper = jus.scraper("datajud", politica={"busca": {"timeout": timeout}})
    assert scraper._perfis_http["busca"].timeout == esperado  # noqa: SLF001


@pytest.mark.parametrize("ajuste", ["abc", 5, None, [("timeout", 90)]])
def test_politica_com_ajuste_que_nao_e_dict_levanta(ajuste):
    # Sem pular o ajuste que não é dict, a checagem de campos itera o valor:
    # ``"abc"`` viraria "recebido ['a', 'b', 'c']" e ``5`` viraria ``TypeError``.
    with pytest.raises(ValueError, match="deve ser um dict de campos"):
        jus.scraper("datajud", politica={"busca": ajuste})


@pytest.mark.parametrize(
    "ajuste",
    # Com campo recusado ou ``timeout`` inválido, o erro ainda é o do perfil:
    # a mensagem de campo citaria um perfil que o DataJud não declara.
    [{"timeout": 90}, {"max_retries": 5}, {"timeout": -1}],
)
def test_politica_com_perfil_desconhecido_levanta(ajuste):
    with pytest.raises(ValueError, match="Perfil HTTP desconhecido"):
        jus.scraper("datajud", politica={"listagem": ajuste})


# ---------------------------------------------------------------------------
# Aviso de paginação interrompida
# ---------------------------------------------------------------------------


def test_falha_na_primeira_pagina_lanca_erro_parcial_com_diagnostico(monkeypatch):
    _instalar_paginas(monkeypatch, [None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP")

    mensagem = str(exc_info.value)
    assert "página 1. Resultados parciais retornados: nenhum registro recebido" in mensagem
    assert "data_ajuizamento_inicio" in mensagem
    assert "politica={'busca': {'timeout'" in mensagem
    assert exc_info.value.resultado.empty
    assert len(exc_info.value.falhas) == 1
    assert isinstance(exc_info.value.falhas[0][2], Exception)
    assert exc_info.value.__cause__ is exc_info.value.falhas[0][2]


def test_falha_no_meio_lanca_erro_parcial_preservando_contagem(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2), None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP", tamanho_pagina=10
        )

    mensagem = str(exc_info.value)
    assert "página 3. Resultados parciais retornados: 20 registro(s) recebido(s) de 25" in mensagem
    assert len(exc_info.value.resultado) == 20
    assert len(exc_info.value.falhas) == 1
    assert isinstance(exc_info.value.falhas[0][2], Exception)
    assert exc_info.value.__cause__ is exc_info.value.falhas[0][2]


def test_total_truncado_pelo_elasticsearch_vira_pelo_menos(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1, total=10000, relation="gte"), None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert "página 2" in str(erro)
    assert "10 registro(s) recebido(s) de pelo menos 10000 encontrado(s)" in str(erro)


def test_contagem_usa_o_tamanho_real_das_paginas(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1, tamanho=20, total=50), None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=20)

    erro = exc_info.value
    assert len(erro.resultado) == 20
    assert "página 2" in str(erro)
    assert "20 registro(s) recebido(s) de 50 encontrado(s)" in str(erro)


def test_total_sem_relation_e_tratado_como_exato(monkeypatch):
    pagina = _pagina(1)
    del pagina["hits"]["total"]["relation"]
    _instalar_paginas(monkeypatch, [pagina, None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert len(erro.resultado) == 10
    assert "página 2" in str(erro)
    assert "10 registro(s) recebido(s) de 25 encontrado(s)" in str(erro)


@pytest.mark.parametrize("total", [None, {}, {"relation": "eq"}])
def test_total_ausente_nao_vira_interrogacao(monkeypatch, total):
    pagina = _pagina(1)
    pagina["hits"]["total"] = total
    _instalar_paginas(monkeypatch, [pagina, None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    mensagem = str(erro)
    assert "10 registro(s) recebido(s); a consulta não informou o total encontrado." in mensagem
    assert "?" not in mensagem
    assert "página 2" in mensagem
    assert len(erro.resultado) == 10


def test_pagina_com_hits_null_apos_pagina_valida_lanca_erro_parcial(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1), {"hits": {"total": {"value": 25}, "hits": None}}])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP", tamanho_pagina=10
        )

    erro = exc_info.value
    mensagem = str(erro)
    assert "api_publica_tjsp" in mensagem
    assert "página 2" in mensagem
    assert "10 registro(s) recebido(s) de 25 encontrado(s)" in mensagem
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"01-{item:02d}" for item in range(10)
    ]
    assert len(erro.falhas) == 1
    assert isinstance(erro.falhas[0][2], Exception)
    assert erro.__cause__ is erro.falhas[0][2]


def test_paginas_descartadas_antes_do_intervalo_nao_contam_como_recebidas(monkeypatch):
    # Com ``paginas=range(2, 4)`` a página 1 é percorrida pelo cursor e
    # descartada; ela não está no DataFrame, então não entra na contagem.
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2), None])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP", tamanho_pagina=10, paginas=range(2, 4)
        )

    erro = exc_info.value
    assert "página 3" in str(erro)
    assert "10 registro(s) recebido(s) de 25" in str(erro)
    assert len(erro.resultado) == 10
    assert erro.resultado["numeroProcesso"].tolist() == [
        f"02-{item:02d}" for item in range(10)
    ]
    assert len(erro.falhas) == 1
