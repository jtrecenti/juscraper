"""Contratos de ``baixar_acordao`` no TJSP, pela movimentação do processo.

Samples de ``tests/fixtures/capture/tjsp.py``: a busca de
1502870-48.2020.8.26.0161 devolve o modal de incidentes com três
``cdProcesso``: a apelação (``RI009HVDD0000``, julgada em 21/09/2026,
documento 16), os embargos 50000 (``RI009HVDD12KW``, acórdão registrado em
30/10/2026, documento 12; o cjsg dá 28/10) e os embargos 50001
(``RI009HVDD12KX``, decisão monocrática). As movimentações vêm do
``carregarMovimentacoesAjax.do``, paginado por cursor.
"""

import copy
import itertools
import logging
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses
from bs4 import BeautifulSoup

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
    # 21 e 19 são do mesmo dia (23/09), um no fim da página 0 e o outro no começo
    # da 1: o deslocamento de ``ordem`` entre páginas põe o 19, mais antigo, antes.
    assert verificados[:2] == [(APELACAO, "19"), (APELACAO, "21")]


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


_MOVIMENTACOES = "acordao/modal_incidentes/movimentacoes_RI009HVDD0000_{}.html"
_LIMITE_DE_PAGINAS = 10


def _registrar_paginacao(segunda_pagina: str) -> list[str]:
    """Processo único (a apelação), com a página 1 real e ``segunda_pagina`` no cursor dela.

    Devolve a lista em que cada pedido de movimentações deixa o cursor. Passado
    :data:`_LIMITE_DE_PAGINAS`, o mock levanta ``AssertionError``: sem a parada,
    o laço não terminaria.
    """
    primeira = load_sample("tjsp", _MOVIMENTACOES.format(0))
    link_mais = re.search(r'linkMaisRecolherMovimentacoes"[^>]*data-cursor="([^"]+)"', primeira)
    assert link_mais is not None
    cursor_inicial = link_mais.group(1)
    pedidos: list[str] = []

    def _responder(request):
        cursor = parse_qs(urlparse(request.url).query).get("cursor", [""])[0]
        pedidos.append(cursor)
        if len(pedidos) > _LIMITE_DE_PAGINAS:
            raise AssertionError("a paginação de movimentações não parou")
        corpo = primeira if not cursor else segunda_pagina.replace("CURSOR_INICIAL", cursor_inicial)
        return 200, {"Content-Type": "text/html;charset=UTF-8"}, corpo

    responses.add(
        responses.GET,
        f"{BASE}cposg/search.do",
        body=load_sample("tjsp", f"acordao/modal_incidentes/show_{APELACAO}.html"),
        content_type="text/html;charset=UTF-8",
    )
    responses.add_callback(responses.GET, f"{BASE}cposg/carregarMovimentacoesAjax.do", callback=_responder)
    return pedidos


@responses.activate
def test_cursor_repetido_para_a_paginacao(tmp_path, mocker):
    mocker.patch("time.sleep")
    segunda = re.sub(
        r'data-cursor="[^"]+"', 'data-cursor="CURSOR_INICIAL"', load_sample("tjsp", _MOVIMENTACOES.format(1))
    )
    pedidos = _registrar_paginacao(segunda)
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(RespostaInesperadaError, match=f"cdProcesso {APELACAO} repetiu o cursor") as erro:
        tjsp.baixar_acordao(CNJ, "01/01/2000")

    assert pedidos[1] in str(erro.value)
    assert len(pedidos) == 2


@responses.activate
def test_pagina_vazia_que_anuncia_outra_para_a_paginacao(tmp_path, mocker):
    mocker.patch("time.sleep")
    vazia = (
        '<table><tr id="metaPaginaMovimentacoes" style="display:none" '
        'data-tem-mais-paginas="true" data-cursor="CURSOR_SEGUINTE"></tr></table>'
    )
    pedidos = _registrar_paginacao(vazia)
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(RespostaInesperadaError, match="veio sem movimentações e com cursor 'CURSOR_SEGUINTE'"):
        tjsp.baixar_acordao(CNJ, "01/01/2000")

    assert len(pedidos) == 2


@responses.activate
def test_empate_de_data_entre_incidentes_fica_com_o_primeiro_da_busca_e_avisa(tmp_path, mocker, caplog):
    # A monocrática responde com as páginas reais dos embargos: os dois
    # incidentes ficam com acórdão em 30/10, o empate que a data não resolve.
    # A última linha real (07/10, sem documento) repetida no topo desloca o
    # acórdão da monocrática para ``ordem`` 1: comparar ``ordem`` entre
    # incidentes escolheria a monocrática, e a regra escolhe os embargos.
    mocker.patch("time.sleep")
    pasta = Path(__file__).parent / "samples" / "acordao" / "modal_incidentes"
    html = "text/html;charset=UTF-8"
    pagina = BeautifulSoup((pasta / f"movimentacoes_{EMBARGOS}_0.html").read_text(encoding="utf-8"), "html.parser")
    linhas = pagina.select("tr.movimentacaoProcesso")
    linhas[0].insert_before(copy.copy(linhas[-1]))
    responses.add(
        responses.GET, f"{BASE}cposg/carregarMovimentacoesAjax.do", content_type=html,
        body=str(pagina),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA})],
    )
    responses.add(
        responses.GET, f"{BASE}cposg/verificarAcessoMovimentacao.do", content_type=html,
        body=(pasta / f"verificar_acesso_{EMBARGOS}_12.html").read_bytes(),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA}, strict_match=False)],
    )
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="juscraper.courts._esaj.acordao"):
        caminho = tjsp.baixar_acordao(CNJ, "28/10/2026")

    assert caminho.endswith(f"_{EMBARGOS}_12.pdf")
    assert _consultas("verificarAcessoMovimentacao.do", "cdProcesso", "cdDocumento") == [
        (EMBARGOS, "12"), (MONOCRATICA, "12"),
    ]
    assert f"o incidente {MONOCRATICA} também tem acórdão em 30/10/2026" in caplog.text


@responses.activate
def test_falha_de_rede_na_checagem_do_empate_nao_custa_o_acordao_escolhido(tmp_path, mocker):
    mocker.patch("time.sleep")
    pasta = Path(__file__).parent / "samples" / "acordao" / "modal_incidentes"
    responses.add(
        responses.GET, f"{BASE}cposg/carregarMovimentacoesAjax.do", content_type="text/html;charset=UTF-8",
        body=(pasta / f"movimentacoes_{EMBARGOS}_0.html").read_bytes(),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA})],
    )
    responses.add(
        responses.GET, f"{BASE}cposg/verificarAcessoMovimentacao.do", body=requests.ConnectionError("sem rede"),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA}, strict_match=False)],
    )
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    caminho = tjsp.baixar_acordao(CNJ, "28/10/2026")

    assert caminho.endswith(f"_{EMBARGOS}_12.pdf")
    assert Path(caminho).exists()


@responses.activate
def test_documento_com_senha_no_mesmo_dia_em_outro_incidente_avisa(tmp_path, mocker, caplog):
    mocker.patch("time.sleep")
    pasta = Path(__file__).parent / "samples" / "acordao" / "modal_incidentes"
    responses.add(
        responses.GET, f"{BASE}cposg/carregarMovimentacoesAjax.do", content_type="text/html;charset=UTF-8",
        body=(pasta / f"movimentacoes_{EMBARGOS}_0.html").read_bytes(),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA})],
    )
    responses.add(
        responses.GET, f"{BASE}cposg/verificarAcessoMovimentacao.do", status=403,
        body=load_sample("tjac", "acordao/dois_acordaos/verificar_acesso_P0000213J0000_10.html"),
        match=[responses.matchers.query_param_matcher({"cdProcesso": MONOCRATICA}, strict_match=False)],
    )
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path))

    with caplog.at_level(logging.WARNING, logger="juscraper.courts._esaj.acordao"):
        caminho = tjsp.baixar_acordao(CNJ, "28/10/2026")

    assert caminho.endswith(f"_{EMBARGOS}_12.pdf")
    assert f"o incidente {MONOCRATICA} tem documento com senha em 30/10/2026" in caplog.text


@responses.activate
def test_sleep_time_separa_cada_pedido_da_linha(tmp_path, mocker):
    dormir = mocker.patch("time.sleep")
    # Relógio que anda 0,1 s a cada leitura: entre o carimbo de um pedido e a
    # conferência do seguinte passam 0,1 s, e a espera só completa os 0,4 s restantes.
    relogio = itertools.count(100.0, 0.1)
    mocker.patch("juscraper.courts._esaj.acordao.time.monotonic", side_effect=lambda: next(relogio))
    registrar_rota_acordao("tjsp", "modal_incidentes", BASE, "cposg/")
    tjsp = jus.scraper("tjsp", download_path=str(tmp_path), sleep_time=0.5)

    tjsp.baixar_acordao(CNJ, "28/10/2026")

    esperas = [c.args[0] for c in dormir.call_args_list]
    assert len(esperas) == len(responses.calls) - 1
    assert esperas == pytest.approx([0.4] * len(esperas))
