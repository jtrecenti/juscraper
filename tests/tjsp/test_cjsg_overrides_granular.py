"""Hook de cjsg que o TJSP liga sobre a base eSAJ.

``CJSG_CHROME_UA`` vale ``True`` só no TJSP. O TJAC entra como caminho base,
com o hook desligado. O corpo do POST (``_build_cjsg_body``) e o limite de 120
caracteres já são cobertos por ``test_cjsg_filters_contract.py`` e
``test_query_too_long_contract.py``.
"""
import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample_bytes


def _baixar_duas_paginas(sigla: str, tmp_path, mocker) -> list:
    mocker.patch("time.sleep")
    base = f"https://esaj.{sigla}.jus.br/cjsg"
    responses.add(responses.POST, f"{base}/resultadoCompleta.do", body=b"")
    for pagina in ("01", "02"):
        responses.add(
            responses.GET,
            f"{base}/trocaDePagina.do",
            body=load_sample_bytes(sigla, f"cjsg/results_normal_page_{pagina}.html"),
        )

    jus.scraper(sigla, download_path=str(tmp_path)).cjsg_download("dano moral", paginas=range(1, 3))

    return [chamada.request for chamada in responses.calls]


@responses.activate
@pytest.mark.parametrize(
    ("sigla", "user_agent"),
    [("tjsp", "Mozilla/5.0"), ("tjac", "juscraper/")],
)
def test_user_agent_do_cjsg(tmp_path, mocker, sigla, user_agent):
    requisicoes = _baixar_duas_paginas(sigla, tmp_path, mocker)

    assert all(req.headers["User-Agent"].startswith(user_agent) for req in requisicoes)
