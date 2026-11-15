"""Falha parcial de shards do Elasticsearch no DataJud (refs #489).

A resposta HTTP 200 com ``_shards.failed > 0`` pode vir incompleta, inclusive
com ``hits.hits`` vazio. ``listar_processos`` a trata como coleta parcial.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import ColetaParcialError
from tests._helpers import load_sample


def _shards(failed: int, total: int = 5) -> dict[str, int]:
    return {"total": total, "successful": total - failed, "skipped": 0, "failed": failed}


def _pagina(
    pagina: int, *, tamanho: int = 10, total: int = 25, falhos: int = 0
) -> dict[str, Any]:
    hits = [
        {"_source": {"numeroProcesso": numero}, "sort": [f"cursor-{numero}"]}
        for numero in _numeros(pagina, tamanho)
    ]
    return {
        "timed_out": False,
        "_shards": _shards(falhos),
        "hits": {"total": {"value": total, "relation": "eq"}, "hits": hits},
    }


def _instalar_paginas(monkeypatch, paginas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chamadas: list[dict[str, Any]] = []
    respostas = iter(paginas)

    def falso(**kwargs: Any) -> dict[str, Any]:
        chamadas.append(kwargs)
        return next(respostas)

    monkeypatch.setattr(datajud_client, "call_datajud_api", falso)
    monkeypatch.setattr(datajud_client.time, "sleep", lambda _: None)
    return chamadas


def _numeros(pagina: int, tamanho: int = 10) -> list[str]:
    return [f"{pagina:02d}-{item:02d}" for item in range(tamanho)]


def test_sem_falha_de_shards_mantem_comportamento_normal(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2), _pagina(3, tamanho=5)])

    df = jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    assert df["numeroProcesso"].tolist() == _numeros(1) + _numeros(2) + _numeros(3, 5)


def test_resposta_vazia_sem_falha_de_shards_e_busca_sem_resultados(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1, tamanho=0, total=0)])

    df = jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP")

    assert df.empty


def test_resposta_vazia_com_falha_de_shards_levanta_coleta_parcial(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1, tamanho=0, total=0, falhos=1)])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP")

    erro = exc_info.value
    mensagem = str(erro)
    assert "'api_publica_tjsp'" in mensagem
    assert "página 1" in mensagem
    assert "1 de 5 shard(s) falharam" in mensagem
    assert erro.resultado.empty
    assert len(erro.falhas) == 1
    assert erro.__cause__ is erro.falhas[0][2]


def test_falha_de_shards_com_hits_preserva_paginas_anteriores_e_a_propria(monkeypatch):
    chamadas = _instalar_paginas(
        monkeypatch, [_pagina(1), _pagina(2, falhos=4), _pagina(3, tamanho=5)],
    )

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    mensagem = str(erro)
    assert erro.resultado["numeroProcesso"].tolist() == _numeros(1) + _numeros(2)
    assert "'api_publica_tjsp' na página 2" in mensagem
    assert "20 registro(s) recebido(s) de 25" in mensagem
    assert "4 de 5 shard(s) falharam" in mensagem
    # O cursor da página incompleta não é usado para seguir adiante.
    assert len(chamadas) == 2


def test_falha_de_shards_em_pagina_vazia_antes_do_total_menciona_shards(monkeypatch):
    _instalar_paginas(monkeypatch, [_pagina(1), _pagina(2, tamanho=0, falhos=2)])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert erro.resultado["numeroProcesso"].tolist() == _numeros(1)
    assert "página 2" in str(erro)
    assert "2 de 5 shard(s) falharam" in str(erro)


def test_falha_de_shards_com_hits_que_nao_parseiam_preserva_anteriores(monkeypatch):
    pagina2 = _pagina(2, falhos=1)
    del pagina2["hits"]["hits"][4]["_source"]
    _instalar_paginas(monkeypatch, [_pagina(1), pagina2])

    with pytest.raises(ColetaParcialError) as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    erro = exc_info.value
    assert erro.resultado["numeroProcesso"].tolist() == _numeros(1)
    assert "página 2" in str(erro)
    assert "1 de 5 shard(s) falharam" in str(erro)


def test_falha_de_shards_em_pagina_descartada_por_paginas_levanta(monkeypatch):
    chamadas = _instalar_paginas(
        monkeypatch, [_pagina(1, falhos=1), _pagina(2), _pagina(3, tamanho=5)],
    )

    with pytest.raises(ColetaParcialError, match=r"página 1\..*1 de 5 shard") as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(
            tribunal="TJSP", paginas=range(2, 4), tamanho_pagina=10,
        )

    assert exc_info.value.resultado.empty
    assert len(chamadas) == 1


@pytest.mark.parametrize("shards", [None, {}])
def test_shards_ausente_ou_sem_falha_nao_levanta(monkeypatch, shards):
    pagina = _pagina(1, tamanho=3, total=3)
    if shards is None:
        del pagina["_shards"]
    else:
        pagina["_shards"] = shards
    _instalar_paginas(monkeypatch, [pagina])

    df = jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    assert df["numeroProcesso"].tolist() == _numeros(1, 3)


def test_sample_real_com_shards_falhos_preserva_os_hits(monkeypatch):
    """Sample real (20 shards, ``failed: 0``) com a falha que a issue relata aplicada."""
    sample = json.loads(load_sample("datajud", "listar_processos/results_normal_page_01.json"))
    sample["_shards"].update(successful=16, failed=4)
    _instalar_paginas(monkeypatch, [sample])

    with pytest.raises(ColetaParcialError, match="4 de 20 shard") as exc_info:
        jus.scraper("datajud", verbose=0).listar_processos(tribunal="TJSP", tamanho_pagina=10)

    esperados = [hit["_source"]["numeroProcesso"] for hit in sample["hits"]["hits"]]
    assert exc_info.value.resultado["numeroProcesso"].tolist() == esperados
