"""Contratos offline do ``cpopg`` do TJPE (PJe ConsultaPública + AWS WAF).

O fluxo de busca, detalhe e parse é o da família ``_trf``, já coberto pelos
contratos do TRF1/TRF3/TRF5; aqui ficam o que o TJPE tem de próprio: o host,
o formulário capturado do TJPE e o cookie do AWS WAF obtido só quando o
desafio aparece. As respostas de busca e de detalhe reaproveitam os samples
do TRF1, porque o HTML do PJe é o mesmo e nenhum dado de processo do TJPE
precisa entrar no repositório.
"""
from __future__ import annotations

from urllib.parse import parse_qsl

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import WafChallengeError
from juscraper.core.waf import USER_AGENT, WAF_COOKIE
from juscraper.courts.tjpe.consulta_publica import TJPEConsultaPublicaScraper
from tests._helpers import load_sample, load_sample_bytes

BASE = "https://pje.cloud.tjpe.jus.br/1g/"
LIST_URL = BASE + "ConsultaPublica/listView.seam"
DETAIL_URL = BASE + "ConsultaPublica/DetalheProcessoConsultaPublica/listView.seam"
CNJ = "00000011220248170001"
CNJ_FORMATADO = "0000001-12.2024.8.17.0001"


@pytest.fixture
def tjpe(mocker):
    """``TJPEScraper`` com a consulta pública sem pausa entre requisições."""
    scraper = jus.scraper("tjpe")
    mocker.patch.object(scraper, "_consulta_publica", TJPEConsultaPublicaScraper(sleep_time=0))
    return scraper


@pytest.fixture
def obter(mocker):
    return mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token", return_value="token-novo"
    )


def _form(status: int = 200):
    responses.add(
        responses.GET,
        LIST_URL,
        body=load_sample_bytes("tjpe", "cpopg/form_initial.html"),
        status=status,
        content_type="text/html;charset=ISO-8859-1",
    )


def _desafio(method: str = responses.GET, url: str = LIST_URL):
    responses.add(
        method,
        url,
        body=load_sample("tjpe", "cpopg/waf_challenge.html"),
        status=202,
        content_type="text/html; charset=UTF-8",
    )


def _busca(sample: str = "cpopg/search_one_result.html"):
    responses.add(
        responses.POST,
        LIST_URL,
        body=load_sample("trf1", sample),
        content_type="text/xml; charset=utf-8",
    )


def _detalhe():
    responses.add(
        responses.GET,
        DETAIL_URL,
        body=load_sample_bytes("trf1", "cpopg/detail_normal.html"),
        content_type="text/html",
    )


@responses.activate
def test_cpopg_sem_desafio_nao_chama_o_playwright(tjpe, obter):
    _form()
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_not_called()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == CNJ
    assert row["processo"] is not None
    assert {"classe", "polo_ativo", "movimentacoes", "documentos"} <= set(df.columns)
    enviado = dict(parse_qsl(responses.calls[1].request.body, keep_blank_values=True))
    assert enviado[
        "fPP:numProcesso-inputNumeroProcessoDecoration:numProcesso-inputNumeroProcesso"
    ] == CNJ_FORMATADO
    # IDs JSF do formulário capturado do TJPE, não os do TRF1.
    assert enviado["fPP:j_id245"] == "fPP:j_id245"
    assert "fPP:j_id163:processoReferenciaInput" in enviado


@responses.activate
def test_processo_ausente_ou_em_segredo_vira_linha_so_com_id_cnj(tjpe, obter):
    _form()
    _busca("cpopg/search_no_results.html")

    df = tjpe.cpopg(CNJ)

    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == CNJ
    assert pd.isna(df.iloc[0].get("processo")) or df.iloc[0].get("processo") is None


@responses.activate
def test_desafio_renova_o_cookie_e_repete_a_requisicao(tjpe, obter):
    _desafio()
    _form()
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_called_once_with(LIST_URL, tribunal="TJPE")
    assert df.iloc[0]["processo"] is not None
    assert "Cookie" not in responses.calls[0].request.headers
    assert responses.calls[1].request.headers["Cookie"] == f"{WAF_COOKIE}=token-novo"
    assert responses.calls[1].request.url == LIST_URL


@responses.activate
def test_desafio_no_meio_da_conversa_repete_o_mesmo_post(tjpe, obter):
    _form()
    _desafio(responses.POST)
    _busca()
    _detalhe()

    df = tjpe.cpopg(CNJ)

    obter.assert_called_once()
    assert df.iloc[0]["processo"] is not None
    posts = [c.request for c in responses.calls if c.request.method == "POST"]
    assert len(posts) == 2
    assert posts[0].body == posts[1].body


@responses.activate
def test_desafio_repetido_depois_da_renovacao_interrompe_o_lote(tjpe, obter):
    _desafio()
    _desafio()

    with pytest.raises(WafChallengeError, match="TJPE"):
        tjpe.cpopg([CNJ, CNJ])

    obter.assert_called_once()


@responses.activate
def test_sem_playwright_o_erro_chega_ao_usuario(tjpe, mocker):
    mocker.patch(
        "juscraper.courts.tjpe.consulta_publica.obter_waf_token",
        side_effect=ImportError("Instale com `pip install 'juscraper[waf]'`"),
    )
    _desafio()

    # Sem a propagação, o ImportError viraria linha só com id_cnj, como processo ausente.
    with pytest.raises(ImportError, match=r"juscraper\[waf\]"):
        tjpe.cpopg(CNJ)


def test_sessao_usa_o_user_agent_do_navegador_que_resolve_o_desafio():
    scraper = TJPEConsultaPublicaScraper(sleep_time=0)
    assert scraper.session.headers["User-Agent"] == USER_AGENT


def test_cjsg_continua_em_sessao_propria(tjpe):
    assert tjpe.session is not tjpe._consulta().session
    assert tjpe.session.headers["User-Agent"] != USER_AGENT


def test_cpopg_rejeita_kwarg_desconhecido(tjpe):
    with pytest.raises(TypeError, match="unexpected keyword"):
        tjpe.cpopg(CNJ, filtro_inexistente="x")


def test_mensagem_de_formulario_inesperado_cita_o_tribunal():
    from juscraper.courts._trf.download import extract_form_field_ids

    with pytest.raises(RuntimeError, match=r"^TJPE: could not locate"):
        extract_form_field_ids("<html></html>", tribunal="TJPE")
