"""Contratos de ``baixar_acordao`` no TJSP, pela movimentação do processo.

Samples de ``tests/fixtures/capture/tjsp.py``: a busca de
1502870-48.2020.8.26.0161 devolve o modal de incidentes com três
``cdProcesso``: a apelação (``RI009HVDD0000``, julgada em 21/09/2026,
documento 16), os embargos 50000 (``RI009HVDD12KW``, acórdão registrado em
30/10/2026, documento 12; o cjsg dá 28/10) e os embargos 50001
(``RI009HVDD12KX``, decisão monocrática). As movimentações vêm do
``carregarMovimentacoesAjax.do``, paginado por cursor.
"""

from urllib.parse import parse_qs, urlparse

import pytest
import responses

import juscraper as jus
from juscraper.courts._esaj.acordao import RespostaInesperadaError
from tests._helpers import load_sample, registrar_rota_acordao

BASE = "https://esaj.tjsp.jus.br/"
CNJ = "1502870-48.2020.8.26.0161"
APELACAO, EMBARGOS, MONOCRATICA = "RI009HVDD0000", "RI009HVDD12KW", "RI009HVDD12KX"


@pytest.fixture
def tjsp(tmp_path, mocker):
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    return scraper


def _consultas(rota, *chaves):
    return [
        tuple(parse_qs(urlparse(c.request.url).query).get(chave, [""])[0] for chave in chaves)
        for c in responses.calls
        if urlparse(c.request.url).path.endswith(rota)
    ]


@responses.activate
def test_data_do_cjsg_escolhe_os_embargos_registrados_depois(tjsp):
    caminho = tjsp.baixar_acordao(CNJ, "28/10/2026")

    assert caminho.endswith(f"15028704820208260161_{EMBARGOS}_12.pdf")
    assert _consultas("show.do", "processo.codigo") == [(APELACAO,), (EMBARGOS,), (MONOCRATICA,)]
    # A primeira página de cada processo já termina antes de 28/10: nenhum cursor seguido.
    assert _consultas("carregarMovimentacoesAjax.do", "cdProcesso", "cursor") == [
        (APELACAO, ""),
        (EMBARGOS, ""),
        (MONOCRATICA, ""),
    ]
    assert _consultas("verificarAcessoMovimentacao.do", "cdProcesso", "cdDocumento") == [(EMBARGOS, "12")]
    # Movimentações carregadas antes de qualquer verificação (o TJSP só libera documento já listado).
    rotas = [urlparse(c.request.url).path.rsplit("/", 1)[-1] for c in responses.calls]
    assert rotas.index("verificarAcessoMovimentacao.do") > max(
        i for i, rota in enumerate(rotas) if rota == "carregarMovimentacoesAjax.do"
    )


@responses.activate
def test_pagina_ate_passar_da_data_e_baixa_a_apelacao(tjsp):
    caminho = tjsp.baixar_acordao(CNJ, "21/09/2026")

    assert caminho.endswith(f"_{APELACAO}_16.pdf")
    paginas = [cd for cd, _ in _consultas("carregarMovimentacoesAjax.do", "cdProcesso", "cursor")]
    # Apelação: a página 1 ainda chega a 21/09 e a 2 passa dela; embargos até o fim.
    assert paginas.count(APELACAO) == 3
    assert paginas.count(EMBARGOS) == 3
    assert paginas.count(MONOCRATICA) == 2
    assert _consultas("verificarAcessoMovimentacao.do", "cdDocumento") == [("16",)]


@responses.activate
def test_pula_certidoes_despachos_e_monocratica_pelo_tipo_na_pasta(tjsp):
    caminho = tjsp.baixar_acordao(CNJ, "22/09/2026")

    assert caminho.endswith(f"_{EMBARGOS}_12.pdf")
    verificados = _consultas("verificarAcessoMovimentacao.do", "cdProcesso", "cdDocumento")
    assert verificados[-1] == (EMBARGOS, "12")
    assert (MONOCRATICA, "4") in verificados
    assert set(verificados[:2]) == {(APELACAO, "19"), (APELACAO, "21")}


@responses.activate
def test_verificar_acesso_sem_url_para_em_vez_de_pular_para_outro_acordao(tmp_path, mocker):
    mocker.patch("time.sleep")
    responses.add(
        responses.GET,
        f"{BASE}cposg/verificarAcessoMovimentacao.do",
        body=load_sample("tjsp", "acordao/verificar_acesso_nao_listado.html"),
        content_type="text/html;charset=UTF-8",
        match=[responses.matchers.query_param_matcher({"cdDocumento": "16"}, strict_match=False)],
    )
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(RespostaInesperadaError, match="documento 16 não devolveu a URL") as erro:
        tjsp.baixar_acordao(CNJ, "21/09/2026")

    assert erro.value.motivo == "resposta_inesperada"
    assert not list(tmp_path.rglob("*.pdf"))
