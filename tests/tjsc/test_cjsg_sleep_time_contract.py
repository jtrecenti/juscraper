"""Regressão: ``sleep_time`` do construtor chega ao ``time.sleep`` do manager.

Antes da #250 esta onda, o ``cjsg_download_manager`` do TJSC tinha um
``time.sleep(1)`` literal dentro da closure ``_get_page``, ignorando o
``self.sleep_time`` herdado de ``HTTPScraper``. Este teste garante que
o valor do construtor chega ao ``time.sleep`` real, evitando regressão
em refatorações futuras (ex.: esquecer ``sleep_time=self.sleep_time``
no ``cjsg_download``).
"""
import responses
from responses.matchers import urlencoded_params_matcher

import juscraper as jus
from juscraper.courts.tjsc.download import build_cjsg_form_body, cjsg_url_for_page
from tests._helpers import load_sample_bytes

SLEEP_VALUE = 0.42


def _add_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        cjsg_url_for_page(pagina),
        body=load_sample_bytes("tjsc", sample_path),
        status=200,
        content_type="text/html; charset=iso-8859-1",
        match=[urlencoded_params_matcher(
            build_cjsg_form_body(pesquisa, page=pagina), allow_blank=True
        )],
    )


@responses.activate
def test_cjsg_respeita_sleep_time_do_construtor(mocker):
    """Valor passado em ``jus.scraper(..., sleep_time=X)`` aparece em ``time.sleep``."""
    sleep_mock = mocker.patch("time.sleep")
    _add_page("dano moral", 1, "cjsg/results_normal_page_01.html")
    _add_page("dano moral", 2, "cjsg/results_normal_page_02.html")

    jus.scraper("tjsc", sleep_time=SLEEP_VALUE).cjsg(
        "dano moral", paginas=range(1, 3),
    )

    sleep_mock.assert_any_call(SLEEP_VALUE)
    for call in sleep_mock.call_args_list:
        assert call.args == (SLEEP_VALUE,), (
            f"time.sleep chamado com valor inesperado: {call.args!r}"
        )
