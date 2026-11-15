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
from unittest.mock import MagicMock

import pytest
import responses

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import ColetaParcialError

URL = f"{datajud_client.DatajudScraper.BASE_API_URL}/api_publica_tjsp/_search"
TOTAL = 2000
TOTAL_EXATO = {"value": TOTAL, "relation": "eq"}


def _instalar_indice(
    chamadas_com_504: set[int],
    *,
    com_sort: bool = True,
    total_a_partir_da_3a: object = TOTAL_EXATO,
) -> list[int]:
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
            {"_source": {"numeroProcesso": f"{n:04d}"}, **({"sort": [n]} if com_sort else {})}
            for n in range(inicio + 1, fim + 1)
        ]
        total = TOTAL_EXATO if len(sizes) <= 2 else total_a_partir_da_3a
        return 200, {}, json.dumps({"hits": {"total": total, "hits": hits}})

    responses.add_callback(responses.POST, URL, callback=responder)
    return sizes


def _numeros(primeiro: int, ultimo: int) -> list[str]:
    return [f"{n:04d}" for n in range(primeiro, ultimo + 1)]


@pytest.fixture
def scraper():
    return jus.scraper("datajud", verbose=0, sleep_time=0.0)


@contextlib.contextmanager
def _sem_aviso():
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        yield


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
def test_paginas_conta_paginas_do_tamanho_pedido_mesmo_com_504(scraper, paginas, chamada_com_504, esperado):
    _instalar_indice({chamada_com_504} if chamada_com_504 else set())

    with pytest.warns(UserWarning, match="504/timeout") if chamada_com_504 else _sem_aviso():
        df = scraper.listar_processos(tribunal="TJSP", paginas=paginas, tamanho_pagina=400)

    assert df["numeroProcesso"].tolist() == _numeros(*esperado)


@responses.activate
def test_pedacos_apos_504_nao_atravessam_a_fronteira_da_pagina(scraper):
    """Com ``tamanho_pagina`` que não é múltiplo do ``size`` reduzido, a página vem em pedaços iguais.

    O ``size`` reduzido vale também para as páginas seguintes.
    """
    sizes = _instalar_indice({1})

    with pytest.warns(UserWarning, match="504/timeout"):
        df = scraper.listar_processos(tribunal="TJSP", paginas=range(2, 3), tamanho_pagina=450)

    assert df["numeroProcesso"].tolist() == _numeros(451, 900)
    # 504 em size=450; a nova busca usa 450 // 4 = 112. Os 338 que faltam da página 1
    # vêm em 4 pedaços de 84 ou 85, e a página 2 em 5 de 90, sem atravessar a fronteira.
    assert sizes == [450, 112, 85, 85, 84, 84, 90, 90, 90, 90, 90]


@responses.activate
def test_sem_paginas_traz_todos_os_processos_apos_504(scraper):
    _instalar_indice({2})

    with pytest.warns(UserWarning, match="504/timeout"):
        df = scraper.listar_processos(tribunal="TJSP", tamanho_pagina=400)

    assert df["numeroProcesso"].tolist() == _numeros(1, TOTAL)


@responses.activate
def test_barra_de_progresso_conta_paginas_e_nao_pedacos(scraper, monkeypatch):
    _instalar_indice({1})
    tqdm = MagicMock()
    monkeypatch.setattr(datajud_client, "tqdm", tqdm)

    with pytest.warns(UserWarning, match="504/timeout"):
        scraper.listar_processos(tribunal="TJSP", paginas=range(1, 3), tamanho_pagina=400)

    assert sum(chamada.args[0] for chamada in tqdm.return_value.update.call_args_list) == 2


@responses.activate
def test_cursor_ausente_no_meio_da_ultima_pagina_pedida_levanta(scraper):
    """Sem ``sort`` num pedaço cheio, a página pedida fica incompleta: falha, e não resultado curto."""
    _instalar_indice({1}, com_sort=False)

    with pytest.warns(UserWarning, match="504/timeout"), pytest.raises(
        ColetaParcialError, match="cursor search_after ausente",
    ) as exc_info:
        scraper.listar_processos(tribunal="TJSP", paginas=1, tamanho_pagina=400)

    assert len(exc_info.value.resultado) == 100


@responses.activate
def test_total_da_pagina_1_vem_so_do_primeiro_pedaco(scraper):
    """Depois do fallback na página 1, ``hits.total`` dos pedaços seguintes não é revalidado."""
    _instalar_indice({1}, total_a_partir_da_3a="malformado")

    with pytest.warns(UserWarning, match="504/timeout"):
        df = scraper.listar_processos(tribunal="TJSP", paginas=1, tamanho_pagina=400)

    assert df["numeroProcesso"].tolist() == _numeros(1, 400)
