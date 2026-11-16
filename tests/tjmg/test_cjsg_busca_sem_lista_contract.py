"""Páginas da busca do TJMG sem a lista de resultados.

O portal responde HTTP 200 com o erro ``ORA-20000 ... DRG-10599`` nas buscas
sem filtro de data, e com a busca categorizada quando há acórdãos de
repetitivos no resultado. As duas viravam um DataFrame vazio, sem aviso. O
erro do banco levanta logo depois da página 1; a busca categorizada é seguida
nas listas de cada categoria. Samples capturados ao vivo por
``python -m tests.fixtures.capture.tjmg``.

A busca comum com resultados demais também volta sem lista, com o aviso
"muitos resultados" (11.170 no sample; 1.905 ainda são listados). Esse é um
limite do portal à consulta, não um erro disfarçado, e o download o checa
à parte, com ``ValueError``.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import requests
import responses
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.core.base import _texto_ausente_como_none
from juscraper.core.exceptions import ColetaParcialError, HTTPSemanticError
from juscraper.courts.tjmg import TJMGScraper
from juscraper.courts.tjmg.parse import TJMGBuscaSemListaError, cjsg_parse
from tests._helpers import load_sample, load_sample_bytes, query_param_subset_matcher
from tests.tjmg._helpers import SEARCH_URL, add_captcha, add_dwr, add_form

_DATAS = {"data_julgamento_inicio": "01/01/2025", "data_julgamento_fim": "31/12/2025"}


def _pagina(nome: str) -> str:
    # O scraper lê a busca como latin-1 (``resp.encoding = "iso-8859-1"``).
    return load_sample("tjmg", f"cjsg/{nome}", encoding="iso-8859-1")


def _add_busca(sample: str, consulta: dict[str, str] | None = None) -> None:
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample_bytes("tjmg", f"cjsg/{sample}"),
        content_type="text/html; charset=ISO-8859-1",
        match=[query_param_subset_matcher(consulta or {})],
    )


def _add_sessao() -> None:
    """Formulário, captcha e DWR, iguais em toda busca."""
    add_form()
    add_captcha()
    add_dwr()


def _consultas_da_busca() -> list[dict[str, list[str]]]:
    return [parse_qs(urlsplit(c.request.url).query) for c in responses.calls if c.request.url.startswith(SEARCH_URL)]


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_erro_ora_levanta_logo_depois_da_pagina_1(mocker, metodo):
    """O ``cjsg_download`` sozinho também levanta, sem pedir outras páginas."""
    mocker.patch("time.sleep")
    _add_sessao()
    _add_busca("erro_ora.html")

    with pytest.raises(TJMGBuscaSemListaError, match="ORA-20000") as exc:
        getattr(jus.scraper("tjmg"), metodo)("dano moral", paginas=range(1, 4))

    assert "DRG-10599: a coluna não está indexada" in str(exc.value)
    assert isinstance(exc.value, HTTPSemanticError)
    assert len(_consultas_da_busca()) == 1


@pytest.mark.parametrize("metodo", ["cjsg", "cjsg_download"])
@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_muitos_resultados_levanta_value_error_logo_depois_da_pagina_1(mocker, metodo):
    """O aviso "muitos resultados" da busca comum levanta ``ValueError`` sem pedir outras páginas."""
    mocker.patch("time.sleep")
    _add_sessao()
    _add_busca("muitos_resultados.html")

    mensagem = "TJMG returned 'muitos resultados' — refine the search (add date range or narrower terms)."
    with pytest.raises(ValueError, match=f"^{re.escape(mensagem)}$"):
        getattr(jus.scraper("tjmg"), metodo)("dano moral", paginas=range(1, 4), **_DATAS)

    assert len(_consultas_da_busca()) == 1


def _add_busca_categorizada(repetitivos: str = "categorizada_repetitivos.html") -> None:
    _add_sessao()
    _add_busca("categorizada.html", {"numeroRegistro": "1"})
    _add_busca(repetitivos, {"listaClasse": "600", "numeroRegistro": "1"})
    _add_busca("categorizada_acordaos_page_01.html", {"excluirRepetitivos": "true", "numeroRegistro": "1"})


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_busca_categorizada_segue_a_lista_de_cada_categoria(mocker):
    """``paginas`` vale para cada lista: a de repetitivos tem uma página, a de acórdãos, 253."""
    mocker.patch("time.sleep")
    _add_busca_categorizada()
    _add_busca(
        "categorizada_acordaos_page_02.html",
        {"excluirRepetitivos": "true", "numeroRegistro": "11", "totalLinhas": "2522", "paginaNumero": "2"},
    )

    df = jus.scraper("tjmg").cjsg("usucapiao", paginas=range(1, 3), **_DATAS)

    esperado = _texto_ausente_como_none(cjsg_parse([
        _pagina(nome) for nome in (
            "categorizada_repetitivos.html", "categorizada_acordaos_page_01.html", "categorizada_acordaos_page_02.html"
        )
    ]))
    pd.testing.assert_frame_equal(df, esperado)
    assert len(df) == 21
    assert df["processo"].is_unique
    consultas = _consultas_da_busca()
    assert len(consultas) == 4
    for consulta in consultas[1:]:
        assert consulta["palavras"] == ["usucapiao"]
        assert consulta["dataJulgamentoInicial"] == ["01/01/2025"]
        assert consulta["dataJulgamentoFinal"] == ["31/12/2025"]
        assert consulta["linhasPorPagina"] == ["10"]


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_busca_categorizada_com_pagina_que_falha_guarda_as_listas_anteriores(mocker):
    mocker.patch("time.sleep")
    _add_busca_categorizada()
    for _ in range(TJMGScraper.perfis_http["cjsg"].max_retries):
        responses.add(
            responses.GET,
            SEARCH_URL,
            body=requests.ConnectionError("reset"),
            match=[query_param_subset_matcher({"excluirRepetitivos": "true", "numeroRegistro": "11"})],
        )

    falha = r"página 2 da lista 'Acórdãos' falhou.*da lista 'Acórdãos', faltam as páginas \[2, 3\]\.$"
    with pytest.raises(ColetaParcialError, match=falha) as erro:
        jus.scraper("tjmg").cjsg_download("usucapiao", paginas=range(1, 4), **_DATAS)

    assert len(erro.value.resultado) == 11
    assert isinstance(erro.value.__cause__, requests.ConnectionError)


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_busca_categorizada_com_lista_seguinte_que_falha_na_pagina_1(mocker):
    mocker.patch("time.sleep")
    _add_sessao()
    _add_busca("categorizada.html", {"numeroRegistro": "1"})
    _add_busca("categorizada_repetitivos.html", {"listaClasse": "600"})
    for _ in range(TJMGScraper.perfis_http["cjsg"].max_retries):
        responses.add(
            responses.GET,
            SEARCH_URL,
            body=requests.ConnectionError("reset"),
            match=[query_param_subset_matcher({"excluirRepetitivos": "true"})],
        )

    with pytest.raises(ColetaParcialError, match=r"página 1 da lista 'Acórdãos'.*faltam a lista inteira\.$") as erro:
        jus.scraper("tjmg").cjsg_download("usucapiao", paginas=[1, 3], **_DATAS)

    assert len(erro.value.resultado) == 1


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_lista_da_busca_categorizada_com_erro_do_banco_levanta(mocker):
    """A página 1 de cada lista passa pela mesma checagem da página 1 da busca."""
    mocker.patch("time.sleep")
    _add_busca_categorizada(repetitivos="erro_ora.html")

    with pytest.raises(TJMGBuscaSemListaError, match="ORA-20000"):
        jus.scraper("tjmg").cjsg_download("usucapiao", paginas=1, **_DATAS)


@pytest.mark.usefixtures("mock_txtcaptcha")
@responses.activate(registry=OrderedRegistry)
def test_busca_categorizada_com_link_sem_parametro_proprio_levanta(mocker):
    """Sem o parâmetro que distingue a lista, segui-la repetiria a busca categorizada."""
    mocker.patch("time.sleep")
    _add_sessao()
    pagina = load_sample_bytes("tjmg", "cjsg/categorizada.html").replace(b"&amp;&amp;listaClasse=600", b"")
    responses.add(responses.GET, SEARCH_URL, body=pagina, content_type="text/html; charset=ISO-8859-1")

    with pytest.raises(TJMGBuscaSemListaError, match="categorizada"):
        jus.scraper("tjmg").cjsg_download("usucapiao", paginas=1, **_DATAS)
    assert len(_consultas_da_busca()) == 1


def test_parse_busca_categorizada_levanta_com_as_contagens():
    """Páginas baixadas antes de o ``cjsg_download`` seguir as listas."""
    with pytest.raises(TJMGBuscaSemListaError, match="categorizada") as exc:
        cjsg_parse([_pagina("categorizada.html")])

    assert "Acórdãos de Repetitivos: 1; Acórdãos: 2522" in str(exc.value)


@pytest.mark.parametrize(
    "sample",
    [
        "no_results.html",
        "single_page.html",
        "results_normal_page_01.html",
        "categorizada_repetitivos.html",
        "categorizada_acordaos_page_01.html",
    ],
)
def test_parse_nao_confunde_paginas_comuns_com_busca_sem_lista(sample):
    cjsg_parse([_pagina(sample)])
