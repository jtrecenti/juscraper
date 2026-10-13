"""Unit tests for the TRF3 ``cjsg`` result count, page selection and list check.

The total comes from the ``N ~ TOTAL`` summary (``section.secao-total``); the
fallback is the ``i/TOTAL)`` counter of the first item. Synthetic cases start
from the real samples and remove only the summary or the counters.
"""
from __future__ import annotations

import re

import pytest

from juscraper.courts.trf3.cjsg_download import (
    PAGE_URL,
    _check_lista,
    _paginas_pedidas,
    build_cjsg_payload,
    build_cjsg_session,
    cjsg_download_manager,
    cjsg_n_results,
)
from tests._helpers import load_sample


def _sample(nome: str) -> str:
    return load_sample("trf3", f"cjsg/{nome}")


@pytest.mark.parametrize(
    ("nome", "total"),
    [
        ("results_normal_page_01.html", 591),
        ("results_normal_page_02.html", 591),
        ("single_page.html", 2),
        ("no_results.html", 0),
        ("turmas_recursais_page_01.html", 434),
        ("monocraticas_page_01.html", 845),
        ("monocraticas_turmas_recursais_page_01.html", 194),
        ("acordaos_2012.html", 68),
    ],
)
def test_cjsg_n_results_samples(nome, total):
    assert cjsg_n_results(_sample(nome)) == total


def _sem_resumo(html: str) -> str:
    inicio = html.index('<section class="secao-total">')
    while inicio != -1:
        fim = html.index("</section>", inicio) + len("</section>")
        html = html[:inicio] + html[fim:]
        inicio = html.find('<section class="secao-total">')
    assert "secao-total" not in html
    return html


def test_cjsg_n_results_fallback_pelo_contador_do_item():
    assert cjsg_n_results(_sem_resumo(_sample("results_normal_page_01.html"))) == 591


def test_cjsg_n_results_fallback_sem_resultados():
    assert cjsg_n_results(_sem_resumo(_sample("no_results.html"))) == 0


def test_cjsg_n_results_pagina_sem_lista_devolve_none():
    """The opening tab has no result list; dates in it must not pass for a total."""
    assert cjsg_n_results(_sample("index_acordaos.html")) is None


def test_paginas_pedidas_none_baixa_todas():
    assert _paginas_pedidas(None, 3) == [1, 2, 3]


def test_paginas_pedidas_none_sem_resultados_baixa_so_a_primeira():
    assert _paginas_pedidas(None, 0) == [1]


def test_paginas_pedidas_none_sem_total_levanta():
    with pytest.raises(ValueError, match="total de resultados"):
        _paginas_pedidas(None, None)


def test_paginas_pedidas_corta_alem_do_total_e_mantem_ordem():
    assert _paginas_pedidas([3, 1, 5, 2], 3) == [3, 1, 2]


LISTAS = [
    "results_normal_page_01.html",
    "results_normal_page_02.html",
    "single_page.html",
    "acordaos_2012.html",
    "turmas_recursais_page_01.html",
    "monocraticas_page_01.html",
    "monocraticas_turmas_recursais_page_01.html",
    "no_results.html",
]


@pytest.mark.parametrize("nome", LISTAS)
def test_check_lista_aceita_todos_os_samples_de_lista(nome):
    """No false positive: every captured list page, zero hits included, passes."""
    _check_lista(_sample(nome), PAGE_URL)


@pytest.mark.parametrize(
    "html",
    [
        pytest.param(_sample("index_acordaos.html"), id="formulario"),
        pytest.param("<html><body><h1>Sistema em manutencao</h1></body></html>", id="manutencao"),
        pytest.param("", id="corpo_vazio"),
    ],
)
def test_check_lista_rejeita_pagina_que_nao_e_a_lista(html):
    """A 200 that is not the list raises, naming the URL it came from."""
    with pytest.raises(RuntimeError, match="não é a lista de resultados") as exc_info:
        _check_lista(html, PAGE_URL + "?np=3")

    assert PAGE_URL + "?np=3" in str(exc_info.value)


class _Resposta:
    """Minimal stand-in for ``requests.Response`` as the manager reads it."""

    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url
        self.status_code = 200
        self.encoding = None


def _lista_sem_total() -> str:
    """A real list page with the summary and the item counters removed."""
    html = re.sub(
        r'<span class="contagem">.*?</span>',
        "",
        _sem_resumo(_sample("results_normal_page_01.html")),
        flags=re.DOTALL,
    )
    assert cjsg_n_results(html) is None
    return html


def _baixar(pagina: str, paginas):
    chamadas: list[tuple[str, str]] = []

    def request_fn(method, url, **kwargs):
        chamadas.append((method, url))
        return _Resposta(pagina, url)

    brutos = cjsg_download_manager(
        build_cjsg_payload("medicamento"),
        base="acordaos",
        paginas=paginas,
        tamanho_pagina=10,
        request_fn=request_fn,
        session=build_cjsg_session(),
        sleep_time=0,
        progress=lambda pedidas, **_: pedidas,
    )
    return brutos, chamadas


def test_manager_lista_sem_total_legivel_mantem_o_pedido():
    """An unreadable total keeps the explicit request only for a recognized list.

    The page has documents, so it passes the list check; without a total there
    is nothing to cut the request by, and the three pages are downloaded.
    """
    pagina = _lista_sem_total()

    brutos, chamadas = _baixar(pagina, range(1, 4))

    assert brutos == [pagina] * 3
    assert len(chamadas) == 2 + 2


def test_manager_lista_sem_total_legivel_e_paginas_none_levanta():
    """``paginas=None`` needs the total; a list without one says so."""
    with pytest.raises(ValueError, match="total de resultados"):
        _baixar(_lista_sem_total(), None)


def test_manager_sem_total_e_sem_lista_levanta_mesmo_com_paginas_explicitas():
    """The opening tab has no total either, but it is not a list: no page is kept."""
    with pytest.raises(RuntimeError, match="não é a lista de resultados"):
        _baixar(_sample("index_acordaos.html"), range(1, 4))


@pytest.mark.parametrize(("tamanho_pagina", "n_paginas"), [(10, 60), (30, 20), (50, 12)])
def test_manager_arredonda_paginas_para_cima(tamanho_pagina, n_paginas):
    """591 hits do not divide by the page size; the last partial page is downloaded.

    Requests: the tab GET, the POST (whose redirect is page 1) and one GET per
    page from 2 on.
    """
    primeira = _sample("results_normal_page_01.html")
    chamadas: list[tuple[str, str]] = []

    def request_fn(method, url, **kwargs):
        chamadas.append((method, url))
        return _Resposta(primeira, url)

    brutos = cjsg_download_manager(
        build_cjsg_payload("medicamento", tamanho_pagina=tamanho_pagina),
        base="acordaos",
        paginas=None,
        tamanho_pagina=tamanho_pagina,
        request_fn=request_fn,
        session=build_cjsg_session(),
        sleep_time=0,
        progress=lambda pedidas, **_: pedidas,
    )

    assert len(brutos) == n_paginas
    assert len(chamadas) == 2 + (n_paginas - 1)
