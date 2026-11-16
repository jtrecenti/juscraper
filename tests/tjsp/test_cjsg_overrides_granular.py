"""Hooks de cjsg que o TJSP liga sobre a base eSAJ.

``CJSG_CHROME_UA`` e ``CJSG_EXTRACT_CONVERSATION_ID`` valem ``True`` só no
TJSP. O TJAC entra como caminho base, com os dois desligados. O corpo do POST
(``_build_cjsg_body``) e o limite de 120 caracteres já são cobertos por
``test_cjsg_filters_contract.py`` e ``test_query_too_long_contract.py``.

Nenhuma primeira página capturada traz ``conversationId`` preenchido; o teste
acrescenta o input ao sample real para exercitar o repasse.
"""
import pytest
import responses

import juscraper as jus
from tests._helpers import load_sample_bytes

CONVERSATION_ID = b'<input type="hidden" name="conversationId" value="abc123">'


def _baixar_duas_paginas(sigla: str, tmp_path, mocker) -> list:
    mocker.patch("time.sleep")
    base = f"https://esaj.{sigla}.jus.br/cjsg"
    primeira = load_sample_bytes(sigla, "cjsg/results_normal_page_01.html")
    responses.add(responses.POST, f"{base}/resultadoCompleta.do", body=b"")
    responses.add(responses.GET, f"{base}/trocaDePagina.do", body=primeira + CONVERSATION_ID)
    responses.add(
        responses.GET, f"{base}/trocaDePagina.do", body=load_sample_bytes(sigla, "cjsg/results_normal_page_02.html")
    )

    jus.scraper(sigla, download_path=str(tmp_path)).cjsg_download("dano moral", paginas=range(1, 3))

    return [chamada.request for chamada in responses.calls]


@responses.activate
@pytest.mark.parametrize(
    ("sigla", "conversation_id"),
    [("tjsp", "abc123"), ("tjac", None)],
)
def test_conversation_id_da_primeira_pagina_segue_para_as_seguintes(tmp_path, mocker, sigla, conversation_id):
    requisicoes = _baixar_duas_paginas(sigla, tmp_path, mocker)

    por_pagina = {req.params["pagina"]: req.params for req in requisicoes if req.method == "GET"}
    assert "conversationId" not in por_pagina["1"]
    assert por_pagina["2"].get("conversationId") == conversation_id


@responses.activate
@pytest.mark.parametrize(
    ("sigla", "user_agent"),
    [("tjsp", "Mozilla/5.0"), ("tjac", "juscraper/")],
)
def test_user_agent_do_cjsg(tmp_path, mocker, sigla, user_agent):
    requisicoes = _baixar_duas_paginas(sigla, tmp_path, mocker)

    assert all(req.headers["User-Agent"].startswith(user_agent) for req in requisicoes)
