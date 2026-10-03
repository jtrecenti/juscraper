"""Contrato de falha do PDPJ sobre a política HTTP do core.

Métodos com uma linha por item (``cpopg``, ``documentos``, ``movimentos``,
``partes``, ``existe`` com lista e ``download_documents``) devolvem a linha de
falha com ``motivo_falha`` e emitem um ``UserWarning`` agregado; o 401
interrompe, com as falhas anteriores numa nota do erro. ``existe`` com ``str``,
``contar`` e ``pesquisa`` levantam o erro.

A fixture ``esperas_do_backoff`` (``conftest.py``) troca o ``time.sleep`` do
core por um mock, e os testes de backoff leem as esperas dele.
"""
from __future__ import annotations

import io
import json
import logging
import warnings
from dataclasses import replace

import pandas as pd
import pytest
import requests
import responses

import juscraper as jus
from juscraper.aggregators._pdpj_sso.renovacao import SsoPdpjIndisponivelError
from juscraper.aggregators.pdpj.client import PdpjScraper
from juscraper.aggregators.pdpj.download import BASE_URL, USER_AGENT, fetch_documento_binario_url
from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError
from juscraper.core.failures import STATUS_CONSULTA_FALHA
from juscraper.core.http import RequestPolicy
from tests._helpers import load_sample

FAKE_TOKEN = (
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0."
    "eyJzdWIiOiJ0ZXN0IiwiZXhwIjo5OTk5OTk5OTk5LCJpYXQiOjE3MDAwMDAwMDB9."
)
PROC = "10029886420194014100"
OUTRO = "00000011120248260100"

# Método -> (sufixo do endpoint, sample do processo que responde bem).
METODOS_DE_LISTA = {
    "cpopg": ("", "cpopg/processo_encontrado.json"),
    "documentos": ("/documentos", "documentos/lista_normal.json"),
    "movimentos": ("/movimentos", "movimentos/lista_normal.json"),
    "partes": ("/partes", "partes/lista_normal.json"),
}


def _mk_scraper(**kwargs):
    s = jus.scraper("pdpj", sleep_time=0, **kwargs)
    s.auth(FAKE_TOKEN)
    return s


def _mock(path: str, status: int = 200, body: str | bytes | Exception = "", content_type: str = "application/json"):
    responses.add(responses.GET, f"{BASE_URL}{path}", body=body, status=status, content_type=content_type)


def _mock_sample(path: str, sample: str) -> None:
    _mock(path, body=load_sample("pdpj", sample))


def _urls() -> list[str]:
    return [call.request.url for call in responses.calls]


# ---------------------------------------------------------------------
# perfis HTTP
# ---------------------------------------------------------------------

def test_perfis_http_declarados():
    comum = RequestPolicy(
        max_retries=6,
        base_backoff=2.0,
        retryable_statuses=frozenset({429, 500, 502, 503, 504}),
        retry_on_timeout=True,
        retry_on_connection_error=False,
    )
    assert PdpjScraper.perfis_http == {
        "listagem": replace(comum, timeout=30.0),
        "documento": replace(comum, timeout=60.0),
    }


@responses.activate
def test_backoff_do_perfil_espera_de_2_a_32_segundos(esperas_do_backoff):
    _mock(f"/processos/{PROC}", status=503)

    with pytest.warns(UserWarning, match="retry_esgotado_503"):
        _mk_scraper().cpopg(PROC)

    assert len(responses.calls) == 6
    assert [chamada.args[0] for chamada in esperas_do_backoff.call_args_list] == [2.0, 4.0, 8.0, 16.0, 32.0]


@responses.activate
def test_timeout_de_cada_perfil_chega_a_requisicao():
    _mock_sample(f"/processos/{PROC}/documentos", "documentos/lista_normal.json")
    _mock(f"/processos/{PROC}/documentos/doc-a/texto", body="texto", content_type="text/plain")
    s = _mk_scraper()

    s.documentos(PROC)
    s.download_documents(pd.DataFrame([{"processo": PROC, "numero_processo": PROC, "id_documento": "doc-a"}]))

    assert [call.request.req_kwargs["timeout"] for call in responses.calls] == [30.0, 60.0]


# Cada ``fetch_*`` com o perfil que usa e uma chamada que o exercita. Um
# ``timeout=`` literal em qualquer um deles venceria o perfil e anularia o ajuste.
_FETCHES = {
    "existe": ("listagem", f"/processos/{PROC}/existe", "true", lambda s: s.existe(PROC)),
    "cpopg": ("listagem", f"/processos/{PROC}", "[]", lambda s: s.cpopg(PROC)),
    "documentos": ("listagem", f"/processos/{PROC}/documentos", "{}", lambda s: s.documentos(PROC)),
    "movimentos": ("listagem", f"/processos/{PROC}/movimentos", "{}", lambda s: s.movimentos(PROC)),
    "partes": ("listagem", f"/processos/{PROC}/partes", "{}", lambda s: s.partes(PROC)),
    "pesquisa": ("listagem", "/processos", '{"content": []}', lambda s: s.pesquisa(paginas=1)),
    "contar": ("listagem", "/processos:contar", "0", lambda s: s.contar()),
    "texto": (
        "documento", f"/processos/{PROC}/documentos/doc-a/texto", "t",
        lambda s: s.download_documents(_docs_df()),
    ),
    "binario": (
        "documento", f"/processos/{PROC}/documentos/doc-a/binario", "b",
        lambda s: s.download_documents(_docs_df(), with_text=False, with_binary=True),
    ),
}


@pytest.mark.parametrize("fetch", list(_FETCHES))
@responses.activate
def test_politica_sobrepoe_o_timeout_do_perfil_em_cada_endpoint(fetch):
    """Sem ``timeout=`` literal nas chamadas, o ajuste do usuário chega à requisição."""
    perfil, caminho, corpo, chamar = _FETCHES[fetch]
    _mock(caminho, body=corpo)
    s = _mk_scraper(politica={perfil: {"timeout": 7}})

    chamar(s)

    assert responses.calls[0].request.req_kwargs["timeout"] == 7
    # Os perfis mesclados não têm acessor público.
    assert s._perfis_http[perfil].max_retries == 6  # noqa: SLF001


def test_fetch_documento_binario_url_usa_o_perfil_documento():
    chamadas = []

    def request_fn(_method, _url, **kwargs):
        chamadas.append(kwargs)
        resposta = requests.Response()
        resposta.status_code = 200
        resposta.raw = io.BytesIO(b'"https://temporaria"')
        return resposta

    assert fetch_documento_binario_url(request_fn, PROC, "doc-a") == "https://temporaria"
    assert chamadas == [{"perfil": "documento"}]


@responses.activate
def test_user_agent_de_navegador_e_accept():
    """A API recusa User-Agent que não é de navegador, e o default do core é ``juscraper/<versão>``."""
    _mock(f"/processos/{PROC}/existe", body="true")

    _mk_scraper().existe(PROC)

    headers = responses.calls[0].request.headers
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Accept"] == "application/json, text/plain, */*"


@pytest.mark.parametrize("status", [500, 502, 504])
@responses.activate
def test_5xx_passa_a_ser_retentado(status):
    responses.add(responses.GET, f"{BASE_URL}/processos/{PROC}/existe", status=status)
    responses.add(responses.GET, f"{BASE_URL}/processos/{PROC}/existe", body="true", status=200)

    assert _mk_scraper().existe(PROC) is True
    assert len(responses.calls) == 2


@responses.activate
def test_timeout_e_retentado_e_depois_vira_motivo():
    _mock(f"/processos/{PROC}", body=requests.ReadTimeout("lento"))

    with pytest.warns(UserWarning, match=f"processo {PROC}: timeout"):
        df = _mk_scraper().cpopg(PROC)

    assert len(responses.calls) == 6
    assert df.iloc[0]["motivo_falha"] == "timeout"
    assert df.iloc[0]["status_consulta"] == STATUS_CONSULTA_FALHA


@responses.activate
def test_timeout_seguido_de_resposta_nao_e_falha():
    responses.add(responses.GET, f"{BASE_URL}/processos/{PROC}", body=requests.ReadTimeout("lento"))
    _mock_sample(f"/processos/{PROC}", "cpopg/processo_encontrado.json")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df = _mk_scraper().cpopg(PROC)

    assert df.iloc[0]["sigla_tribunal"] == "TRF1"
    assert df.iloc[0]["motivo_falha"] is None


@responses.activate
def test_403_numa_requisicao_so_nos_metodos_de_lista():
    _mock(f"/processos/{PROC}/partes", status=403)

    with pytest.warns(UserWarning, match="http_403"):
        df = _mk_scraper().partes(PROC)

    assert len(responses.calls) == 1
    assert df.iloc[0]["motivo_falha"] == "http_403"


# ---------------------------------------------------------------------
# linha de falha nos métodos por processo
# ---------------------------------------------------------------------

@pytest.mark.parametrize("metodo", list(METODOS_DE_LISTA))
@responses.activate
def test_404_vira_linha_nao_encontrado_e_o_outro_processo_segue(metodo):
    sufixo, sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{OUTRO}{sufixo}", status=404)
    _mock_sample(f"/processos/{PROC}{sufixo}", sample)

    with pytest.warns(UserWarning, match="falharam") as avisos:
        df = getattr(_mk_scraper(), metodo)([OUTRO, PROC])

    falha = df[df["processo"] == OUTRO]
    assert len(falha) == 1
    assert falha.iloc[0]["motivo_falha"] == "nao_encontrado"
    sucesso = df[df["processo"] == PROC]
    assert len(sucesso) >= 1
    assert sucesso["motivo_falha"].isna().all()
    assert len(avisos) == 1
    mensagem = str(avisos[0].message)
    assert f"PdpjScraper.{metodo}: 1 consulta(s) de processo falharam" in mensagem
    assert f"processo {OUTRO}: nao_encontrado" in mensagem


@responses.activate
def test_404_no_cpopg_e_linha_de_falha_nao_encontrado():
    """O 404 é ausência medida, mas sai na linha de falha, com o motivo; a lista vazia segue sem motivo."""
    _mock(f"/processos/{OUTRO}", status=404)
    _mock_sample(f"/processos/{PROC}", "cpopg/processo_nao_encontrado.json")

    with pytest.warns(UserWarning, match="nao_encontrado"):
        df = _mk_scraper().cpopg([OUTRO, PROC])

    assert df["status_consulta"].tolist() == [STATUS_CONSULTA_FALHA, "Nao encontrado"]
    assert df["motivo_falha"].tolist() == ["nao_encontrado", None]
    assert df["detalhes"].tolist() == [None, None]


@responses.activate
def test_existe_lista_404_vira_linha_com_existe_none():
    _mock(f"/processos/{OUTRO}/existe", status=404)
    _mock(f"/processos/{PROC}/existe", body="true")

    with pytest.warns(UserWarning, match=f"processo {OUTRO}: nao_encontrado"):
        df = _mk_scraper().existe([OUTRO, PROC])

    assert df.columns.tolist() == ["processo", "existe", "motivo_falha"]
    assert df["existe"].tolist() == [None, True]
    assert df["motivo_falha"].tolist() == ["nao_encontrado", None]


@responses.activate
def test_conexao_caida_vira_motivo_sem_retry():
    _mock(f"/processos/{PROC}/movimentos", body=requests.ConnectionError("recusada"))

    with pytest.warns(UserWarning, match="conexao"):
        df = _mk_scraper().movimentos(PROC)

    assert len(responses.calls) == 1
    assert df.iloc[0]["motivo_falha"] == "conexao"


@pytest.mark.parametrize("metodo", list(METODOS_DE_LISTA))
@responses.activate
def test_401_interrompe_com_as_falhas_anteriores_na_nota(metodo):
    """Sem aviso: com avisos promovidos a erro, o aviso trocaria o 401 durante a propagação."""
    sufixo, _sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{OUTRO}{sufixo}", status=404)
    _mock(f"/processos/{PROC}{sufixo}", status=401)

    with pytest.raises(requests.HTTPError) as erro:
        getattr(_mk_scraper(), metodo)([OUTRO, PROC])

    assert erro.value.response.status_code == 401
    notas = " ".join(getattr(erro.value, "__notes__", []))
    assert "Antes do 401, 1 consulta(s) de processo falharam" in notas
    assert f"processo {OUTRO}: nao_encontrado" in notas


@responses.activate
def test_401_no_existe_lista_interrompe():
    _mock(f"/processos/{PROC}/existe", status=401)

    with pytest.raises(requests.HTTPError):
        _mk_scraper().existe([PROC])


@responses.activate
def test_excecao_fora_do_vocabulario_propaga():
    _mock(f"/processos/{PROC}", body=requests.TooManyRedirects("laço"))

    with pytest.raises(requests.TooManyRedirects):
        _mk_scraper().cpopg(PROC)


# ---------------------------------------------------------------------
# forma errada da resposta
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    ['{"numeroProcesso": "1002988-64.2019.4.01.4100"}', "<html>manutenção</html>", "null"],
    ids=["objeto-no-lugar-da-lista", "nao-json", "null"],
)
@responses.activate
def test_cpopg_forma_errada_vira_json_invalido(body):
    _mock(f"/processos/{PROC}", body=body)

    with pytest.warns(UserWarning, match="json_invalido"):
        df = _mk_scraper().cpopg(PROC)

    assert df.iloc[0]["motivo_falha"] == "json_invalido"
    assert df.iloc[0]["status_consulta"] == STATUS_CONSULTA_FALHA
    # Forma errada não é status transitório: uma requisição só.
    assert len(responses.calls) == 1


@pytest.mark.parametrize("metodo", ["documentos", "movimentos", "partes"])
@responses.activate
def test_lista_no_lugar_do_objeto_vira_json_invalido(metodo):
    sufixo, _sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{PROC}{sufixo}", body="[]")

    with pytest.warns(UserWarning, match="json_invalido"):
        df = getattr(_mk_scraper(), metodo)(PROC)

    esperado: dict[str, str | None] = {"processo": PROC, "motivo_falha": "json_invalido"}
    if metodo == "documentos":
        esperado = {"processo": PROC, "id_documento": None, "motivo_falha": "json_invalido"}
    assert df.to_dict("records") == [esperado]


@responses.activate
def test_existe_resposta_sem_true_ou_false():
    _mock(f"/processos/{PROC}/existe", body='{"existe": true}')
    s = _mk_scraper()

    with pytest.raises(InvalidJSONResponseError):
        s.existe(PROC)
    with pytest.warns(UserWarning, match="json_invalido"):
        df = s.existe([PROC])
    assert df.iloc[0]["motivo_falha"] == "json_invalido"
    assert df.iloc[0]["existe"] is None


@pytest.mark.parametrize("body", ["muitos", "true", "4.5", '{"total": "3"}', '{"total": true}', "[]"])
@responses.activate
def test_contar_sem_inteiro_levanta_json_invalido(body):
    _mock("/processos:contar", body=body)

    with pytest.raises(InvalidJSONResponseError):
        _mk_scraper().contar(tribunal="TRF1")


# ---------------------------------------------------------------------
# métodos sem linha por item levantam
# ---------------------------------------------------------------------

@responses.activate
def test_existe_str_levanta_em_vez_de_false():
    _mock(f"/processos/{PROC}/existe", status=500)

    with pytest.raises(RetryExhaustedError) as erro:
        _mk_scraper().existe(PROC)

    assert erro.value.status_code == 500


@responses.activate
def test_existe_str_404_levanta():
    _mock(f"/processos/{PROC}/existe", status=404)

    with pytest.raises(requests.HTTPError):
        _mk_scraper().existe(PROC)


@responses.activate
def test_contar_levanta_em_vez_de_zero():
    _mock("/processos:contar", status=503)

    with pytest.raises(RetryExhaustedError):
        _mk_scraper().contar(tribunal="TRF1")


@responses.activate
def test_contar_zero_legitimo():
    _mock("/processos:contar", body="0")

    assert _mk_scraper().contar(tribunal="TRF1") == 0


@responses.activate
def test_pesquisa_levanta_na_falha_da_pagina_2():
    """Antes, a página que falhava virava lista vazia e encerrava o laço com as anteriores."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        body=load_sample("pdpj", "pesquisa/single_page.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(responses.GET, f"{BASE_URL}/processos", status=500)

    with pytest.raises(RetryExhaustedError):
        _mk_scraper().pesquisa(tribunal="TRF1", paginas=2)

    assert "searchAfter" in _urls()[1]


@responses.activate
def test_pesquisa_pagina_sem_content_levanta_em_vez_de_truncar():
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        body=load_sample("pdpj", "pesquisa/single_page.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(responses.GET, f"{BASE_URL}/processos", json={"content": None, "searchAfter": None}, status=200)

    with pytest.raises(InvalidJSONResponseError):
        _mk_scraper().pesquisa(tribunal="TRF1", paginas=2)


@responses.activate
def test_pesquisa_pagina_terminal_com_content_null_e_zero_elementos_encerra():
    """A última página traz ``searchAfter`` preenchido, e a seguinte pode vir com ``content: null``."""
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        body=load_sample("pdpj", "pesquisa/single_page.json"),
        status=200,
        content_type="application/json",
    )
    responses.add(
        responses.GET,
        f"{BASE_URL}/processos",
        json={"content": None, "numberOfElements": 0, "searchAfter": None},
        status=200,
    )

    df = _mk_scraper().pesquisa(tribunal="TRF1")

    assert len(df) == 1
    assert len(responses.calls) == 2


@pytest.mark.parametrize(
    "pagina",
    [
        {"numberOfElements": 0},
        {"content": None, "numberOfElements": False},
        {"content": None, "numberOfElements": 0.0},
        {"content": None, "numberOfElements": "0"},
        {"content": None},
    ],
    ids=["sem_content", "zero_bool", "zero_float", "zero_str", "sem_contagem"],
)
@responses.activate
def test_pesquisa_so_aceita_null_com_zero_inteiro_explicito(pagina):
    _mock("/processos", body=json.dumps(pagina))

    with pytest.raises(InvalidJSONResponseError):
        _mk_scraper().pesquisa(tribunal="TRF1", paginas=1)


@responses.activate
def test_cpopg_item_que_nao_e_objeto_vira_json_invalido():
    _mock(f"/processos/{PROC}", body="[null]")

    with pytest.warns(UserWarning, match="json_invalido"):
        df = _mk_scraper().cpopg(PROC)

    assert df.iloc[0]["motivo_falha"] == "json_invalido"
    assert df.iloc[0]["status_consulta"] == STATUS_CONSULTA_FALHA


@pytest.mark.parametrize("metodo", ["documentos", "movimentos", "partes"])
@responses.activate
def test_motivo_falha_e_a_ultima_coluna_mesmo_com_a_falha_primeiro(metodo):
    sufixo, sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{OUTRO}{sufixo}", status=404)
    _mock_sample(f"/processos/{PROC}{sufixo}", sample)

    with pytest.warns(UserWarning, match="falharam"):
        df = getattr(_mk_scraper(), metodo)([OUTRO, PROC])

    with pytest.warns(UserWarning, match="falharam"):
        df_sucesso_primeiro = getattr(_mk_scraper(), metodo)([PROC, OUTRO])

    assert df.columns[-1] == "motivo_falha"
    assert df.columns[0] == "processo"
    assert list(df.columns) == list(df_sucesso_primeiro.columns)


@responses.activate
def test_download_de_documentos_que_so_falharam_devolve_vazio(caplog):
    _mock(f"/processos/{PROC}/documentos", status=404)
    s = _mk_scraper()
    with pytest.warns(UserWarning, match="falharam"):
        docs = s.documentos(PROC)

    with caplog.at_level(logging.WARNING, logger="juscraper.aggregators.pdpj.client"):
        out = s.download_documents(docs)

    assert out.empty
    assert len(responses.calls) == 1
    # A falha já saiu no aviso de ``documentos``; o log de "documento sem id" não a repete.
    assert "sem id_documento" not in caplog.text


@responses.activate
def test_pesquisa_forma_errada_levanta():
    _mock("/processos", body="[]")

    with pytest.raises(InvalidJSONResponseError):
        _mk_scraper().pesquisa(tribunal="TRF1", paginas=1)


# ---------------------------------------------------------------------
# texto e binário
# ---------------------------------------------------------------------

def _docs_df() -> pd.DataFrame:
    return pd.DataFrame([{"processo": PROC, "numero_processo": PROC, "id_documento": "doc-a"}])


@responses.activate
def test_texto_e_binario_falhando_com_motivos_diferentes():
    _mock(f"/processos/{PROC}/documentos/doc-a/texto", status=404, content_type="text/plain")
    _mock(f"/processos/{PROC}/documentos/doc-a/binario", status=500, content_type="text/plain")

    with pytest.warns(UserWarning, match="falharam") as avisos:
        out = _mk_scraper().download_documents(_docs_df(), with_binary=True)

    linha = out.iloc[0]
    assert linha["texto"] is None
    assert linha["binario"] is None
    assert linha["motivo_falha"] == "http_404"
    mensagem = str(avisos[0].message)
    assert "2 download(s) de documento falharam" in mensagem
    assert "doc-a, texto: http_404" in mensagem
    assert "doc-a, binario: retry_esgotado_500" in mensagem


@responses.activate
def test_texto_falho_com_binario_bom_guarda_o_motivo_do_texto():
    _mock(f"/processos/{PROC}/documentos/doc-a/texto", status=403, content_type="text/plain")
    _mock(f"/processos/{PROC}/documentos/doc-a/binario", body=b"%PDF", content_type="application/pdf")

    with pytest.warns(UserWarning, match="doc-a, texto: http_403"):
        out = _mk_scraper().download_documents(_docs_df(), with_binary=True)

    assert out.iloc[0]["texto"] is None
    assert out.iloc[0]["binario"] == b"%PDF"
    assert out.iloc[0]["motivo_falha"] == "http_403"


@responses.activate
def test_download_json_invalido_nao_se_aplica_ao_texto():
    """Texto e binário não são JSON: um 200 qualquer é conteúdo."""
    _mock(f"/processos/{PROC}/documentos/doc-a/texto", body="[]", content_type="text/plain")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = _mk_scraper().download_documents(_docs_df())

    assert out.iloc[0]["texto"] == "[]"
    assert out.iloc[0]["motivo_falha"] is None


# ---------------------------------------------------------------------
# origem do aviso
# ---------------------------------------------------------------------

@pytest.mark.parametrize("metodo", list(METODOS_DE_LISTA))
@responses.activate
def test_aviso_aponta_para_quem_chamou_o_metodo(metodo):
    sufixo, _sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{PROC}{sufixo}", status=404)

    with pytest.warns(UserWarning, match="falharam") as avisos:
        getattr(_mk_scraper(), metodo)(PROC)

    assert avisos[0].filename == __file__


@responses.activate
def test_aviso_do_download_aponta_para_quem_chamou_o_metodo():
    _mock(f"/processos/{PROC}/documentos/doc-a/texto", status=404, content_type="text/plain")

    with pytest.warns(UserWarning, match="falharam") as avisos:
        _mk_scraper().download_documents(_docs_df())

    assert avisos[0].filename == __file__


@pytest.mark.parametrize("metodo", list(METODOS_DE_LISTA))
@responses.activate
def test_falha_do_sso_interrompe_com_as_falhas_anteriores_na_nota(metodo):
    """A renovação do token falha na segunda requisição, como faria o ``AuthPdpj``."""
    sufixo, _sample = METODOS_DE_LISTA[metodo]
    _mock(f"/processos/{OUTRO}{sufixo}", status=404)
    scraper = _mk_scraper()
    chamadas = {"n": 0}

    def auth(requisicao):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise SsoPdpjIndisponivelError("O SSO do PJe respondeu HTTP 503 ao renovar o token; tente de novo.")
        return requisicao

    scraper.session.auth = auth

    with pytest.raises(SsoPdpjIndisponivelError) as erro:
        getattr(scraper, metodo)([OUTRO, PROC])

    notas = " ".join(getattr(erro.value, "__notes__", []))
    assert "Antes da falha do SSO, 1 consulta(s) de processo falharam" in notas
