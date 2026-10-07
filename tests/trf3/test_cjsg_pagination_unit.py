"""Unit tests for the TRF3 ``cjsg`` result count and page selection.

The total comes from the ``N ~ TOTAL`` summary (``section.secao-total``); the
fallback is the ``i/TOTAL)`` counter of the first item. Synthetic cases start
from the real samples and remove only the summary.
"""
from __future__ import annotations

import pytest

from juscraper.courts.trf3.cjsg_download import (
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


def test_paginas_pedidas_sem_total_mantem_pedido():
    assert _paginas_pedidas(range(2, 5), None) == [2, 3, 4]


class _Resposta:
    """Minimal stand-in for ``requests.Response`` as the manager reads it."""

    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url
        self.status_code = 200
        self.encoding = None


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
