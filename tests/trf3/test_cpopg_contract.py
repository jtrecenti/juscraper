"""Contratos offline do ``TRF3Scraper.cpopg`` (API JSON da consulta pública).

A camada HTTP é simulada com ``responses`` a partir dos samples gravados por
``tests/fixtures/capture/trf3.py``. Os matchers conferem o número buscado, o
parâmetro ``page`` de cada página e o cabeçalho ``x-pagina-origem``.
"""
from __future__ import annotations

import pandas as pd
import pytest
import requests
import responses
from responses import matchers

import juscraper as jus
from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts.trf3.download import BASE_URL_1G, busca_url, recurso_url
from juscraper.courts.trf3.schemas import OutputCpopgTRF3
from tests.trf3._api import carregar, id_processo_do_cenario, itens_do_cenario, registrar_busca, registrar_processo

COLUNAS = {
    "id_cnj",
    "processo",
    "classe",
    "assunto",
    "data_distribuicao",
    "orgao_julgador",
    "orgao_julgador_colegiado",
    "jurisdicao",
    "endereco_orgao",
    "polo_ativo",
    "polo_passivo",
    "outros_interessados",
    "movimentacoes",
    "documentos",
}
CNJ_PAGINADO = "50035362120254036342"
CNJ_SEM_RESULTADO = "00000000020994030000"


@pytest.fixture(autouse=True)
def _sem_espera(mocker):
    """Zera as esperas de paginação e de backoff do retry."""
    mocker.patch("time.sleep")


def _row_sem_dados(row: pd.Series) -> bool:
    return all(pd.isna(row.get(col)) for col in COLUNAS - {"id_cnj"})


@responses.activate
def test_cpopg_paginado_traz_todas_as_paginas_e_colunas() -> None:
    """Movimentações em 5 páginas viram uma lista só, com as colunas do portal antigo."""
    paginas = registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0).cpopg("5003536-21.2025.4.03.6342")

    assert len(df) == 1
    assert set(df.columns) >= COLUNAS
    row = df.iloc[0]
    assert row["id_cnj"] == CNJ_PAGINADO
    assert row["processo"] == "5003536-21.2025.4.03.6342"
    assert row["classe"] == "PROCEDIMENTO DO JUIZADO ESPECIAL CÍVEL (436)"
    assert row["data_distribuicao"] == "24/09/2025"
    assert row["orgao_julgador"] == "1ª Vara Gabinete JEF de Barueri"
    assert row["orgao_julgador_colegiado"] is None  # "" na API

    movs = row["movimentacoes"]
    total = carregar("cpopg", "paginado_movimentacoes_page_0.json")["pageInfo"]["count"]
    assert len(movs) == total == len(itens_do_cenario("cpopg", "paginado", "movimentacoes"))
    assert set(movs[0]) == {"data", "descricao", "documento"}
    assert movs[0]["data"] == "24/09/2026 11:38:16"

    autor = row["polo_ativo"][0]
    assert autor["nome"] == "CINTIA REGIANE CORREA DOS SANTOS"
    assert autor["tipo"] == "AUTOR"
    assert autor["participante"].startswith("CINTIA REGIANE")
    assert autor["situacao"] == "Ativo"
    assert row["polo_passivo"][0]["procuradoria"] == "Procuradoria-Regional Federal da 3ª Região"
    assert row["outros_interessados"][0]["tipo"] == "FISCAL DA LEI"

    doc = row["documentos"][0]
    assert doc["data"] == "22/09/2026 13:33:36"
    assert doc["descricao"] == "SENTENÇA (SENTENÇA)"
    assert doc["binario"] is False
    assert doc["id"] == carregar("cpopg", "paginado_documentos_page_0.json")["result"][0]["id"]

    OutputCpopgTRF3.model_validate(row.to_dict())
    # Cada página registrada foi pedida exatamente uma vez: busca + dados + páginas.
    assert len(responses.calls) == 2 + paginas


@responses.activate
def test_cpopg_recurso_vazio_vira_lista_vazia_sem_pedir_outra_pagina() -> None:
    """``pageInfo.last = 0`` (polo ativo vazio) não dispara ``page=1``."""
    paginas = registrar_processo(BASE_URL_1G, "cpopg", "normal")
    df = jus.scraper("trf3", sleep_time=0).cpopg("5021122-65.2018.4.03.6100")

    row = df.iloc[0]
    assert row["processo"] == "5021122-65.2018.4.03.6100"
    assert row["polo_ativo"] == []
    assert row["polo_passivo"][0]["tipo"] == "EXECUTADO"
    assert len(row["movimentacoes"]) == carregar("cpopg", "normal_movimentacoes_page_0.json")["pageInfo"]["count"]
    assert len(responses.calls) == 2 + paginas


@responses.activate
def test_cpopg_recurso_com_erro_http_vira_none_e_mantem_o_resto() -> None:
    """A API responde 500 ao ``poloPassivo`` de alguns mandados de segurança.

    O recurso sai ``None`` (não ``[]``, que significaria "sem partes") e as
    demais colunas do processo continuam preenchidas.
    """
    registrar_processo(BASE_URL_1G, "cpopg", "erro_recurso")
    df = jus.scraper("trf3", sleep_time=0).cpopg("5025507-75.2026.4.03.6100")

    row = df.iloc[0]
    assert row["processo"] == "5025507-75.2026.4.03.6100"
    assert row["polo_passivo"] is None
    assert row["polo_ativo"][0]["tipo"] == "IMPETRANTE"
    assert row["movimentacoes"]
    assert "\n" in row["assunto"] and " \n" not in row["assunto"]
    id_processo = id_processo_do_cenario("cpopg", "erro_recurso")
    url_polo = recurso_url(BASE_URL_1G, id_processo, "poloPassivo")
    tentativas = [c for c in responses.calls if c.request.url.startswith(url_polo)]
    assert len(tentativas) == 4  # perfil "api": 4 tentativas antes de desistir


@responses.activate
def test_cpopg_sem_resultado_vira_linha_so_com_id_cnj() -> None:
    """Busca vazia não pede detalhe; a linha traz só ``id_cnj``."""
    registrar_busca(BASE_URL_1G, "cpopg", "sem_resultado", "0000000-00.2099.4.03.0000")
    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_SEM_RESULTADO)

    assert list(df.columns) == ["id_cnj"]
    assert df.iloc[0]["id_cnj"] == CNJ_SEM_RESULTADO
    assert len(responses.calls) == 1


@responses.activate
def test_cpopg_lote_preserva_ordem() -> None:
    """Lote misto devolve uma linha por CNJ, na ordem de entrada."""
    registrar_busca(BASE_URL_1G, "cpopg", "sem_resultado", "0000000-00.2099.4.03.0000")
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0).cpopg([CNJ_SEM_RESULTADO, CNJ_PAGINADO])

    assert list(df["id_cnj"]) == [CNJ_SEM_RESULTADO, CNJ_PAGINADO]
    assert _row_sem_dados(df.iloc[0])
    assert df.iloc[1]["processo"] == "5003536-21.2025.4.03.6342"


@responses.activate
def test_cpopg_retenta_timeout_de_leitura() -> None:
    """Requisição sem resposta (Akamai segura parte delas) é retentada."""
    responses.add(responses.GET, busca_url(BASE_URL_1G), body=requests.ReadTimeout("sem resposta"))
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert df.iloc[0]["processo"] == "5003536-21.2025.4.03.6342"


@responses.activate
def test_cpopg_lote_segue_apos_erro_de_rede() -> None:
    """Erro de rede que persiste nas tentativas vira linha só com ``id_cnj``."""
    responses.add(
        responses.GET,
        busca_url(BASE_URL_1G),
        body=requests.ConnectionError("caiu"),
        match=[matchers.query_param_matcher({"page": "0", "numeroProcesso": "0000000-00.2099.4.03.0000"})],
    )
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0).cpopg([CNJ_SEM_RESULTADO, CNJ_PAGINADO])

    assert _row_sem_dados(df.iloc[0])
    assert df.iloc[1]["processo"] == "5003536-21.2025.4.03.6342"


@responses.activate
def test_cpopg_lote_segue_apos_erro_de_parse(monkeypatch) -> None:
    """Erro no parser de um item vira linha só com ``id_cnj`` e o lote segue."""
    from juscraper.courts.trf3 import client

    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    registrar_processo(BASE_URL_1G, "cpopg", "normal")
    real = client.parse_processo
    chamadas = {"n": 0}

    def parse_instavel(bruto):
        chamadas["n"] += 1
        if chamadas["n"] == 1:
            raise ValueError("JSON inesperado")
        return real(bruto)

    monkeypatch.setattr(client, "parse_processo", parse_instavel)
    df = jus.scraper("trf3", sleep_time=0).cpopg([CNJ_PAGINADO, "50211226520184036100"])

    assert _row_sem_dados(df.iloc[0])
    assert df.iloc[1]["processo"] == "5021122-65.2018.4.03.6100"


@responses.activate
def test_cpopg_bloqueio_akamai_interrompe_o_lote() -> None:
    """403 ``Access Denied`` do Akamai levanta ``BotChallengeBlockedError`` sem retentar."""
    responses.add(
        responses.GET,
        busca_url(BASE_URL_1G),
        body=(
            b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1>"
            b" Reference&#32;&#35;18&#46;27f62917&#46;1779623119&#46;a59b1f4c</BODY></HTML>"
        ),
        status=403,
        content_type="text/html",
    )
    with pytest.raises(BotChallengeBlockedError) as exc_info:
        jus.scraper("trf3", sleep_time=0).cpopg([CNJ_PAGINADO, CNJ_SEM_RESULTADO])
    assert exc_info.value.tribunal == "TRF3"
    assert exc_info.value.reference == "18.27f62917.1779623119.a59b1f4c"
    assert len(responses.calls) == 1


@responses.activate
def test_cpopg_envia_cabecalhos_de_navegador() -> None:
    """A sessão usa os cabeçalhos de XHR do Chrome, não o User-Agent do juscraper."""
    registrar_busca(BASE_URL_1G, "cpopg", "sem_resultado", "0000000-00.2099.4.03.0000")
    jus.scraper("trf3", sleep_time=0).cpopg(CNJ_SEM_RESULTADO)

    headers = responses.calls[0].request.headers
    assert headers["User-Agent"].startswith("Mozilla/5.0")
    assert headers["Accept"].startswith("application/json")
    assert headers["Sec-Fetch-Mode"] == "cors"
    assert "Upgrade-Insecure-Requests" not in headers


def test_cpopg_rejeita_kwarg_desconhecido() -> None:
    """Kwarg desconhecido vira ``TypeError`` antes de qualquer requisição."""
    scraper = jus.scraper("trf3", sleep_time=0)
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg(CNJ_PAGINADO, filtro_inexistente="x")
    with pytest.raises(TypeError, match="cpopg_download"):
        scraper.cpopg_download(CNJ_PAGINADO, filtro_inexistente="x")


@responses.activate
def test_cpopg_download_e_parse_separados() -> None:
    """``cpopg_download`` devolve os envelopes; ``cpopg_parse`` monta o mesmo DataFrame."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    registrar_busca(BASE_URL_1G, "cpopg", "sem_resultado", "0000000-00.2099.4.03.0000")
    scraper = jus.scraper("trf3", sleep_time=0)
    brutos = scraper.cpopg_download([CNJ_PAGINADO, CNJ_SEM_RESULTADO])

    assert brutos[1] is None
    assert set(brutos[0]) == {"busca", "dados", "poloAtivo", "poloPassivo", "outrosInteressados",
                              "movimentacoes", "documentos"}
    assert len(brutos[0]["movimentacoes"]) == 5
    df = scraper.cpopg_parse(brutos, [CNJ_PAGINADO, CNJ_SEM_RESULTADO])
    assert df.iloc[0]["processo"] == "5003536-21.2025.4.03.6342"
    with pytest.raises(ValueError, match="mesmo tamanho"):
        scraper.cpopg_parse(brutos, [CNJ_PAGINADO])


def test_cpopg_aceita_politica_por_perfil() -> None:
    """``politica=`` ajusta os perfis ``api`` e ``documento`` campo a campo."""
    scraper = jus.scraper("trf3", politica={"api": {"timeout": 5}})
    assert scraper._perfis_http["api"].timeout == 5  # pylint: disable=protected-access
    assert scraper._perfis_http["api"].retry_on_timeout is True  # pylint: disable=protected-access


@responses.activate
def test_cpopg_ignora_resultado_de_outro_numero() -> None:
    """Busca que devolve processo de outro número é tratada como sem resultado."""
    responses.add(
        responses.GET,
        busca_url(BASE_URL_1G),
        json=carregar("cpopg", "paginado_busca.json"),  # traz o 5003536-21.2025.4.03.6342
        match=[matchers.query_param_matcher({"page": "0", "numeroProcesso": "5021122-65.2018.4.03.6100"})],
    )
    df = jus.scraper("trf3", sleep_time=0).cpopg("50211226520184036100")

    assert list(df.columns) == ["id_cnj"]
    assert len(responses.calls) == 1


@pytest.mark.parametrize("id_processo", ["../../v1/outra", "/abs", "a.b", "", None])
@responses.activate
def test_cpopg_id_processo_invalido_vira_erro_do_processo(caplog, id_processo) -> None:
    """``idProcesso`` fora do alfabeto da API não entra em URL: o processo vira linha só com ``id_cnj``."""
    busca = carregar("cpopg", "paginado_busca.json")
    busca["result"][0]["idProcesso"] = id_processo
    responses.add(responses.GET, busca_url(BASE_URL_1G), json=busca)

    with caplog.at_level("WARNING", logger="juscraper.trf3"):
        df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert list(df.columns) == ["id_cnj"]
    assert len(responses.calls) == 1
    assert "idProcesso inválido" in caplog.text


@pytest.mark.parametrize(
    "falha",
    [requests.ReadTimeout("sem resposta"), requests.ConnectionError("caiu")],
    ids=["timeout", "conexao"],
)
@responses.activate
def test_cpopg_erro_de_rede_em_recurso_derruba_o_processo(falha) -> None:
    """Timeout ou erro de conexão que persiste num recurso paginado derruba o processo.

    Só erro HTTP depois das tentativas deixa o recurso ``None``; erro de rede
    não diz nada sobre o recurso e vira linha só com ``id_cnj``.
    """
    id_processo = id_processo_do_cenario("cpopg", "paginado")
    for _ in range(4):  # uma falha por tentativa do perfil "api"
        responses.add(responses.GET, recurso_url(BASE_URL_1G, id_processo, "movimentacoes"), body=falha)
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert list(df.columns) == ["id_cnj"]
    url_movs = recurso_url(BASE_URL_1G, id_processo, "movimentacoes")
    assert sum(c.request.url.startswith(url_movs) for c in responses.calls) == 4


@responses.activate
def test_cpopg_erro_em_dados_derruba_o_processo() -> None:
    """``/dados`` com erro HTTP depois das tentativas derruba o processo, sem pedir os recursos."""
    id_processo = id_processo_do_cenario("cpopg", "paginado")
    registrar_busca(BASE_URL_1G, "cpopg", "paginado", "5003536-21.2025.4.03.6342")
    responses.add(responses.GET, recurso_url(BASE_URL_1G, id_processo, "dados"), status=500, json={"status": 500})

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert list(df.columns) == ["id_cnj"]
    assert len(responses.calls) == 1 + 4
    assert not any("poloAtivo" in c.request.url for c in responses.calls)


@responses.activate
def test_cpopg_envelope_com_status_diferente_de_ok_derruba_o_processo() -> None:
    """``/dados`` com HTTP 200 mas ``status`` diferente de ``"ok"`` não vira processo com dados."""
    id_processo = id_processo_do_cenario("cpopg", "paginado")
    dados = carregar("cpopg", "paginado_dados.json")
    dados["status"] = "error"
    registrar_busca(BASE_URL_1G, "cpopg", "paginado", "5003536-21.2025.4.03.6342")
    responses.add(responses.GET, recurso_url(BASE_URL_1G, id_processo, "dados"), json=dados)

    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert list(df.columns) == ["id_cnj"]
    assert len(responses.calls) == 2


@responses.activate
def test_cpopg_retenta_erro_de_conexao() -> None:
    """O perfil ``api`` retenta erro de conexão, como diz o CHANGELOG."""
    responses.add(responses.GET, busca_url(BASE_URL_1G), body=requests.ConnectionError("caiu"))
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    df = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO)

    assert df.iloc[0]["processo"] == "5003536-21.2025.4.03.6342"


@responses.activate
def test_cpopg_preserva_jurisdicao_endereco_segredo_e_documento_da_movimentacao() -> None:
    """Campos que o parser copia da API saem com o valor capturado, não ``None``."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    row = jus.scraper("trf3", sleep_time=0).cpopg(CNJ_PAGINADO).iloc[0]

    dados = carregar("cpopg", "paginado_dados.json")["result"]
    assert row["jurisdicao"] == dados["jurisdicao"] == "Subseção Judiciária de Barueri (Juizado Especial Federal Cível)"
    assert row["endereco_orgao"] == dados["endereco"]
    assert row["endereco_orgao"].startswith("Avenida Piracema, 1362")
    assert row["polo_ativo"][0]["segredo_justica"] is False
    movs_com_documento = [m for m in row["movimentacoes"] if m["documento"] is not None]
    assert movs_com_documento
    assert row["movimentacoes"][2]["documento"] == "22/09/2026 13:33:36 - Sentença (Sentença)"


@responses.activate
def test_cpopg_parse_aceita_htmls_como_alias_deprecado() -> None:
    """``htmls=`` continua aceito com ``DeprecationWarning`` e produz o mesmo DataFrame de ``brutos=``."""
    registrar_processo(BASE_URL_1G, "cpopg", "paginado")
    scraper = jus.scraper("trf3", sleep_time=0)
    brutos = scraper.cpopg_download(CNJ_PAGINADO)
    canonico = scraper.cpopg_parse(brutos=brutos, id_cnj_list=[CNJ_PAGINADO])

    with pytest.warns(DeprecationWarning, match="'htmls' está deprecado. Use 'brutos'") as avisos:
        via_alias = scraper.cpopg_parse(htmls=brutos, id_cnj_list=[CNJ_PAGINADO])

    pd.testing.assert_frame_equal(via_alias, canonico)
    assert avisos[0].filename == __file__


def test_cpopg_parse_recusa_brutos_e_htmls_juntos() -> None:
    """Canônico e alias juntos levantam ``ValueError`` sem aviso de deprecação."""
    scraper = jus.scraper("trf3", sleep_time=0)
    with pytest.raises(ValueError, match="ao mesmo tempo"):
        scraper.cpopg_parse(brutos=[None], htmls=[None], id_cnj_list=[CNJ_PAGINADO])


def test_cpopg_parse_recusa_html_do_portal_antigo() -> None:
    """HTML passado por posição ou pelo alias levanta ``TypeError`` explicando o formato novo."""
    scraper = jus.scraper("trf3", sleep_time=0)
    html = "<html><body>Detalhe do processo</body></html>"
    with pytest.raises(TypeError, match="envelopes JSON da API"):
        scraper.cpopg_parse([html, None], [CNJ_PAGINADO, CNJ_SEM_RESULTADO])
    with pytest.warns(DeprecationWarning), pytest.raises(TypeError, match="não o HTML do portal antigo"):
        scraper.cpopg_parse(htmls=[html], id_cnj_list=[CNJ_PAGINADO])
    with pytest.raises(TypeError, match="envelopes JSON da API"):
        scraper.cposg_parse([html], [CNJ_PAGINADO])


def test_cpopg_parse_argumentos_ausentes_ou_desconhecidos() -> None:
    """Sem ``brutos``/``id_cnj_list`` ou com kwarg desconhecido, ``TypeError``."""
    scraper = jus.scraper("trf3", sleep_time=0)
    with pytest.raises(TypeError, match="exige brutos e id_cnj_list"):
        scraper.cpopg_parse(id_cnj_list=[CNJ_PAGINADO])
    with pytest.raises(TypeError, match="unexpected keyword"):
        scraper.cpopg_parse([None], [CNJ_PAGINADO], formato="html")
