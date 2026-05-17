"""Regressão: ``sleep_time`` do construtor chega ao ``time.sleep`` do manager.

Antes da #250 esta onda, o ``cjsg_download_manager`` do TJRO tinha um
``time.sleep(1)`` literal dentro da closure ``_get_page``, ignorando o
``self.sleep_time`` herdado de ``HTTPScraper``. Quem passava
``sleep_time=0`` no construtor não tinha efeito. Este teste garante que
o valor do construtor chega ao ``time.sleep`` real, evitando regressão
em refatorações futuras (ex.: esquecer ``sleep_time=self.sleep_time``
no ``cjsg_download``).
"""
import responses
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjro.download import BASE_URL, RESULTS_PER_PAGE, build_cjsg_payload
from tests._helpers import load_sample

SLEEP_VALUE = 0.42


def _add_page(pesquisa: str, pagina_1based: int, sample_path: str) -> None:
    offset = (pagina_1based - 1) * RESULTS_PER_PAGE
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjro", sample_path),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(pesquisa, offset=offset))],
    )


@responses.activate
def test_cjsg_respeita_sleep_time_do_construtor(mocker):
    """Valor passado em ``jus.scraper(..., sleep_time=X)`` aparece em ``time.sleep``."""
    sleep_mock = mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.json")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.json")

    jus.scraper("tjro", sleep_time=SLEEP_VALUE).cjsg(
        "dano moral", paginas=range(1, 3),
    )

    sleep_mock.assert_any_call(SLEEP_VALUE)
    for call in sleep_mock.call_args_list:
        assert call.args == (SLEEP_VALUE,), (
            f"time.sleep chamado com valor inesperado: {call.args!r}"
        )
