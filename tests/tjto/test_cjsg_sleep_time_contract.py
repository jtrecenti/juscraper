"""Regressão: ``sleep_time`` do construtor chega ao ``time.sleep`` do manager.

Antes da #250 esta onda, o ``cjsg_download_manager`` do TJTO tinha um
``time.sleep(1)`` literal no loop de paginação, ignorando o
``self.sleep_time`` herdado de ``HTTPScraper``. Este teste garante que
o valor do construtor chega ao ``time.sleep`` real, evitando regressão
em refatorações futuras (ex.: esquecer ``sleep_time=self.sleep_time``
no ``_download_internal``).
"""
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjto.download import BASE_URL, build_cjsg_payload
from tests._helpers import load_sample

SLEEP_VALUE = 0.42


def _add_post(query: str, *, start: int, sample_path: str, instancia: str = "2") -> None:
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjto", sample_path),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[urlencoded_params_matcher(
            build_cjsg_payload(query, start=start, tip_criterio_inst=instancia),
            allow_blank=True,
        )],
    )


@responses.activate
def test_cjsg_respeita_sleep_time_do_construtor(mocker):
    """Valor passado em ``jus.scraper(..., sleep_time=X)`` aparece em ``time.sleep``."""
    sleep_mock = mocker.patch("time.sleep")
    _add_post("dano moral", start=0, sample_path="cjsg/results_normal_page_01.html")
    _add_post("dano moral", start=20, sample_path="cjsg/results_normal_page_02.html")

    jus.scraper("tjto", sleep_time=SLEEP_VALUE).cjsg(
        "dano moral", paginas=range(1, 3),
    )

    sleep_mock.assert_any_call(SLEEP_VALUE)
    for call in sleep_mock.call_args_list:
        assert call.args == (SLEEP_VALUE,), (
            f"time.sleep chamado com valor inesperado: {call.args!r}"
        )
