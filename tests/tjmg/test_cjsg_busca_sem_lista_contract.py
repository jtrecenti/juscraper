"""Páginas da busca do TJMG sem a lista de resultados levantam erro.

O portal responde HTTP 200 com o erro ``ORA-20000 ... DRG-10599`` nas buscas
sem filtro de data, e com a busca categorizada quando há acórdãos de
repetitivos no resultado. As duas viravam um DataFrame vazio, sem aviso.
Samples capturados ao vivo por ``python -m tests.fixtures.capture.tjmg``.
"""
from __future__ import annotations

import pytest
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.exceptions import HTTPSemanticError
from juscraper.courts.tjmg.parse import TJMGBuscaSemListaError, cjsg_parse
from tests._helpers import load_sample, load_sample_bytes
from tests.tjmg._helpers import SEARCH_URL, add_captcha, add_dwr, add_form


def _pagina(nome: str) -> str:
    # O scraper lê a busca como latin-1 (``resp.encoding = "iso-8859-1"``).
    return load_sample("tjmg", f"cjsg/{nome}", encoding="iso-8859-1")


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_cjsg_sem_data_com_erro_ora_levanta(mocker):
    mocker.patch("time.sleep")
    add_form()
    add_captcha()
    add_dwr()
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample_bytes("tjmg", "cjsg/erro_ora.html"),
        content_type="text/html; charset=ISO-8859-1",
    )

    with pytest.raises(TJMGBuscaSemListaError, match="ORA-20000") as exc:
        jus.scraper("tjmg").cjsg("dano moral", paginas=1)

    assert "DRG-10599: a coluna não está indexada" in str(exc.value)
    assert isinstance(exc.value, HTTPSemanticError)


def test_parse_busca_categorizada_levanta_com_as_contagens():
    with pytest.raises(TJMGBuscaSemListaError, match="categorizada") as exc:
        cjsg_parse([_pagina("categorizada.html")])

    assert "Acórdãos de Repetitivos: 1; Acórdãos: 2522" in str(exc.value)


@pytest.mark.parametrize(
    "sample", ["no_results.html", "single_page.html", "results_normal_page_01.html"]
)
def test_parse_nao_confunde_paginas_comuns_com_busca_sem_lista(sample):
    cjsg_parse([_pagina(sample)])
