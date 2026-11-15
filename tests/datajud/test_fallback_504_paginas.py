"""O fallback de 504 não desloca a numeração de ``paginas`` (#513).

Depois do 504, ``call_datajud_api`` refaz a busca com ``size`` reduzido. A
página pedida é completada em pedaços desse tamanho, e ``paginas`` continua
contando páginas de ``tamanho_pagina``. Os testes passam pelo
``call_datajud_api`` real, com um índice de 2000 processos simulado por
``responses``.
"""
from __future__ import annotations

import contextlib
import json
import warnings

import pytest
import responses

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import ColetaParcialError

URL = f"{datajud_client.DatajudScraper.BASE_API_URL}/api_publica_tjsp/_search"
TOTAL = 2000


def _instalar_indice(chamadas_com_504: set[int]) -> list[int]:
    """Simula o ``_search`` com cursor ``search_after``; devolve os ``size`` pedidos."""
    sizes: list[int] = []

    def responder(request):
        corpo = json.loads(request.body)
        sizes.append(corpo["size"])
        if len(sizes) in chamadas_com_504:
            return 504, {}, ""
        inicio = corpo.get("search_after", [0])[0]
        fim = min(inicio + corpo["size"], TOTAL)
        hits = [
            {"_source": {"numeroProcesso": f"{n:04d}"}, "sort": [n]}
            for n in range(inicio + 1, fim + 1)
        ]
        resposta = {"hits": {"total": {"value": TOTAL, "relation": "eq"}, "hits": hits}}
        return 200, {}, json.dumps(resposta)

    responses.add_callback(responses.POST, URL, callback=responder)
    return sizes


@responses.activate
@pytest.mark.parametrize(
    ("paginas", "chamada_com_504", "esperado"),
    [
        (range(2, 3), None, (401, 800)),
        (range(2, 3), 2, (401, 800)),
        (range(3, 4), 1, (801, 1200)),
        (range(1, 4), 2, (1, 1200)),
    ],
)
def test_paginas_conta_paginas_do_tamanho_pedido_mesmo_com_504(paginas, chamada_com_504, esperado):
    _instalar_indice({chamada_com_504} if chamada_com_504 else set())
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)

    with pytest.warns(UserWarning, match="504/timeout") if chamada_com_504 else _sem_aviso():
        df = scraper.listar_processos(tribunal="TJSP", paginas=paginas, tamanho_pagina=400)

    inicio, fim = esperado
    assert df["numeroProcesso"].tolist() == [f"{n:04d}" for n in range(inicio, fim + 1)]


@responses.activate
def test_pedacos_apos_504_nao_atravessam_a_fronteira_da_pagina():
    """Com ``tamanho_pagina`` que não é múltiplo do ``size`` reduzido, o pedaço final encurta."""
    sizes = _instalar_indice({1})
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)

    with pytest.warns(UserWarning, match="504/timeout"):
        df = scraper.listar_processos(tribunal="TJSP", paginas=range(2, 3), tamanho_pagina=450)

    assert df["numeroProcesso"].tolist() == [f"{n:04d}" for n in range(451, 901)]
    # 504 em size=450; a nova busca usa 450 // 4 = 112, e cada página fecha com um pedaço de 2.
    assert sizes == [450, 112, 112, 112, 112, 2, 112, 112, 112, 112, 2]


@responses.activate
def test_sem_paginas_traz_todos_os_processos_apos_504():
    _instalar_indice({2})
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)

    with pytest.warns(UserWarning, match="504/timeout"):
        df = scraper.listar_processos(tribunal="TJSP", tamanho_pagina=400)

    assert df["numeroProcesso"].tolist() == [f"{n:04d}" for n in range(1, TOTAL + 1)]


@responses.activate
def test_barra_de_progresso_conta_paginas_e_nao_pedacos(monkeypatch):
    _instalar_indice({1})
    atualizacoes: list[int] = []

    class BarraRegistrada:
        def __init__(self, *_args, **_kwargs):
            pass

        def update(self, n):
            atualizacoes.append(n)

        def close(self):
            pass

    monkeypatch.setattr(datajud_client, "tqdm", BarraRegistrada)
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)

    with pytest.warns(UserWarning, match="504/timeout"):
        scraper.listar_processos(tribunal="TJSP", paginas=range(1, 3), tamanho_pagina=400)

    assert sum(atualizacoes) == 2


@responses.activate
def test_cursor_ausente_no_meio_da_ultima_pagina_pedida_levanta():
    """Sem ``sort`` num pedaço cheio, a página pedida fica incompleta: falha, e não resultado curto."""
    chamadas = []

    def responder(request):
        chamadas.append(json.loads(request.body))
        if len(chamadas) == 1:
            return 504, {}, ""
        hits = [{"_source": {"numeroProcesso": f"{n:04d}"}} for n in range(1, 101)]
        return 200, {}, json.dumps({"hits": {"total": {"value": TOTAL, "relation": "eq"}, "hits": hits}})

    responses.add_callback(responses.POST, URL, callback=responder)
    scraper = jus.scraper("datajud", verbose=0, sleep_time=0.0)

    with pytest.warns(UserWarning, match="504/timeout"), pytest.raises(
        ColetaParcialError, match="cursor search_after ausente",
    ) as exc_info:
        scraper.listar_processos(tribunal="TJSP", paginas=1, tamanho_pagina=400)

    assert len(exc_info.value.resultado) == 100


@contextlib.contextmanager
def _sem_aviso():
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        yield
