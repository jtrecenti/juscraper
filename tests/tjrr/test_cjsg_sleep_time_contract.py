"""Regressão: ``sleep_time`` do construtor chega ao ``time.sleep`` do manager.

Antes da #250 esta onda, o ``cjsg_download_manager`` do TJRR tinha três
``time.sleep(1)`` literais (um entre ``_search`` e ``_paginate`` inicial,
mais um por iteração de página), ignorando o ``self.sleep_time``
herdado de ``HTTPScraper``. Este teste garante que o valor do
construtor chega ao ``time.sleep`` real, evitando regressão em
refatorações futuras do pipeline ``client.py`` → manager.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import load_sample, urlencoded_body_subset_matcher
from tests.tjrr._helpers import INDEX_URL, add_get_initial

SLEEP_VALUE = 0.42

_SAMPLES_DIR = Path(__file__).parent / "samples" / "cjsg"
pytestmark = pytest.mark.skipif(
    not (_SAMPLES_DIR / "step_01_consulta.html").exists(),
    reason=(
        "TJRR samples ainda não capturados — rode "
        "`python -m tests.fixtures.capture.tjrr` para popular "
        "tests/tjrr/samples/cjsg/."
    ),
)


def _add_post_initial(sample_path: str):
    responses.add(
        responses.POST,
        INDEX_URL,
        body=load_sample("tjrr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[urlencoded_body_subset_matcher({"menuinicial": "menuinicial"})],
    )


def _add_post_ajax(sample_path: str, first_offset: str):
    responses.add(
        responses.POST,
        INDEX_URL,
        body=load_sample("tjrr", sample_path),
        status=200,
        content_type="application/xml; charset=UTF-8",
        match=[urlencoded_body_subset_matcher({
            "javax.faces.partial.ajax": "true",
            "formPesquisa:j_idt159:dataTablePesquisa_first": first_offset,
        })],
    )


@responses.activate(registry=OrderedRegistry)
def test_cjsg_respeita_sleep_time_do_construtor(mocker):
    """Valor passado em ``jus.scraper(..., sleep_time=X)`` aparece em ``time.sleep``."""
    sleep_mock = mocker.patch("time.sleep")
    add_get_initial()
    _add_post_initial("cjsg/step_02_search.html")
    _add_post_ajax("cjsg/step_03_pagina_02.xml", "10")

    jus.scraper("tjrr", sleep_time=SLEEP_VALUE).cjsg(
        "dano moral", paginas=range(1, 3),
    )

    sleep_mock.assert_any_call(SLEEP_VALUE)
    for call in sleep_mock.call_args_list:
        assert call.args == (SLEEP_VALUE,), (
            f"time.sleep chamado com valor inesperado: {call.args!r}"
        )
