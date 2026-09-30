"""Contrato de falha por linha do JusbrScraper.

Uma requisição que falha em ``cpopg`` ou ``download_documents`` vira linha com
conteúdo ``None`` e a coluna ``motivo_falha`` preenchida, e entra num único
``UserWarning`` ao fim da chamada. O 401 interrompe o lote, com as falhas
anteriores numa nota do erro. O 404 só conta como ausência na listagem, cujo
404 a API usa para CNJ inexistente. Exceção sem motivo no vocabulário de
``juscraper.core.failures`` propaga.
"""
from __future__ import annotations

import json
from typing import Any

import jwt
import pandas as pd
import pytest
import requests
import responses
from responses.matchers import query_param_matcher
from responses.registries import OrderedRegistry

import juscraper as jus
from juscraper.aggregators.jusbr.client import JusbrScraper
from juscraper.core.failures import STATUS_CONSULTA_FALHA
from juscraper.core.http import RETRYABLE_STATUSES
from tests._helpers import load_sample

LIST_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos/"
BASE_TEXT_URL = "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos"
BASE_BINARY_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos"
HMAC_KEY = "0123456789abcdef0123456789abcdef-test"

CNJ_1 = "00000000000000000000"
CNJ_2 = "11111111111111111111"
UUID_TEXT_1 = "11111111-1111-1111-1111-111111111111"
UUID_BIN_1 = "22222222-2222-2222-2222-222222222222"
UUID_TEXT_2 = "33333333-3333-3333-3333-333333333333"


def _jwt(exp: int = 9999999999) -> str:
    encoded: str = jwt.encode({"sub": "tester", "exp": exp}, HMAC_KEY, algorithm="HS256")
    return encoded


@pytest.fixture(autouse=True)
def _sem_pausa(mocker):
    """Neutraliza ``sleep_time`` e o backoff do retry."""
    mocker.patch("time.sleep")


def _scraper() -> JusbrScraper:
    scraper: JusbrScraper = jus.scraper("jusbr", sleep_time=0.0)
    scraper.auth(_jwt())
    return scraper


def _numero_oficial(sample: str) -> str:
    numero: str = json.loads(load_sample("jusbr", sample))["content"][0]["numeroProcesso"]
    return numero


def _add_lista(cnj: str, **kwargs: Any) -> None:
    kwargs.setdefault("content_type", "application/json")
    responses.add(
        responses.GET, LIST_URL, match=[query_param_matcher({"numeroProcesso": cnj})], **kwargs,
    )


def _add_lista_tipica(cnj: str) -> str:
    _add_lista(cnj, body=load_sample("jusbr", "cpopg/typical_single.json"), status=200)
    return _numero_oficial("cpopg/typical_single.json")


def _add_detalhes(numero: str, **kwargs: Any) -> None:
    kwargs.setdefault("content_type", "application/json")
    responses.add(responses.GET, f"{LIST_URL}{numero}", **kwargs)


def _texto_url(uuid: str, cnj: str = CNJ_1) -> str:
    return f"{BASE_TEXT_URL}/{cnj}/documentos/{uuid}/texto"


def _binario_url(uuid: str, cnj: str = CNJ_1) -> str:
    return f"{BASE_BINARY_URL}/{cnj}/documentos/{uuid}/binario"


def _doc(uuid_texto: str | None, uuid_binario: str | None = None, cnj: str = CNJ_1) -> dict[str, Any]:
    meta: dict[str, Any] = {"idDocumento": uuid_texto or uuid_binario}
    if uuid_texto:
        meta["hrefTexto"] = f"/processos/{cnj}/documentos/{uuid_texto}/texto"
    if uuid_binario:
        meta["hrefBinario"] = f"/processos/{cnj}/documentos/{uuid_binario}/binario"
    return meta


def _base_df(documentos: list[dict[str, Any]], cnj: str = CNJ_1) -> pd.DataFrame:
    return pd.DataFrame([{
        "numeroProcesso": cnj,
        "processo": cnj,
        "detalhes": {"dadosBasicos": {"documentos": documentos}},
    }])


def _notas(erro: BaseException) -> str:
    return " ".join(getattr(erro, "__notes__", []))


# ---------------------------------------------------------------------------
# 401: interrompe o lote, com as falhas anteriores na nota
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_cpopg_401_propaga_com_falhas_anteriores_na_nota():
    scraper = _scraper()
    _add_lista(CNJ_1, status=500, json={"erro": "x"})
    _add_lista(CNJ_1, status=500, json={"erro": "x"})
    _add_lista(CNJ_1, status=500, json={"erro": "x"})
    _add_lista(CNJ_2, status=401, json={"erro": "token"})

    with pytest.raises(requests.HTTPError) as erro:
        scraper.cpopg([CNJ_1, CNJ_2])

    assert erro.value.response.status_code == 401
    assert "Antes do 401, 1 consulta(s) de processo falharam" in _notas(erro.value)
    assert f"processo {CNJ_1}, listagem: retry_esgotado_500" in _notas(erro.value)


@responses.activate(registry=OrderedRegistry)
def test_cpopg_401_nos_detalhes_propaga():
    scraper = _scraper()
    numero = _add_lista_tipica(CNJ_1)
    _add_detalhes(numero, status=401, json={"erro": "token"})

    with pytest.raises(requests.HTTPError) as erro:
        scraper.cpopg(CNJ_1)

    assert erro.value.response.status_code == 401
    assert _notas(erro.value) == ""


@responses.activate(registry=OrderedRegistry)
def test_download_documents_401_propaga_com_falhas_anteriores_na_nota():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), status=404)
    responses.add(responses.GET, _texto_url(UUID_TEXT_2), status=401)

    with pytest.raises(requests.HTTPError) as erro:
        scraper.download_documents(_base_df([_doc(UUID_TEXT_1), _doc(UUID_TEXT_2)]))

    assert erro.value.response.status_code == 401
    assert "Antes do 401, 1 download(s) de documento falharam" in _notas(erro.value)
    assert f"documento {UUID_TEXT_1}, texto: http_404" in _notas(erro.value)


@responses.activate(registry=OrderedRegistry)
def test_download_documents_401_no_binario_propaga():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), body="texto", status=200)
    responses.add(responses.GET, _binario_url(UUID_BIN_1), status=401)

    with pytest.raises(requests.HTTPError):
        scraper.download_documents(_base_df([_doc(UUID_TEXT_1, UUID_BIN_1)]))


# ---------------------------------------------------------------------------
# 404: ausência só na listagem
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_cpopg_404_da_listagem_e_ausencia_sem_motivo(recwarn):
    scraper = _scraper()
    _add_lista(CNJ_1, status=404, json={"erro": "Processo não encontrado"})

    df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "status_consulta"] == "Nao encontrado na lista inicial"
    assert df.loc[0, "motivo_falha"] is None
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


@responses.activate(registry=OrderedRegistry)
def test_cpopg_404_nos_detalhes_e_falha_http_404():
    scraper = _scraper()
    numero = _add_lista_tipica(CNJ_1)
    _add_detalhes(numero, status=404, json={"erro": "x"})

    with pytest.warns(UserWarning, match=rf"JusbrScraper.cpopg: 1 consulta\(s\).*{numero}, detalhes: http_404"):
        df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "status_consulta"] == STATUS_CONSULTA_FALHA
    assert df.loc[0, "motivo_falha"] == "http_404"
    assert df.loc[0, "numeroProcessoOficial"] == numero


@responses.activate(registry=OrderedRegistry)
def test_download_documents_404_e_falha_http_404():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), status=404)

    with pytest.warns(UserWarning, match="texto: http_404"):
        df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))

    assert df.loc[0, "texto"] is None
    assert df.loc[0, "motivo_falha"] == "http_404"


# ---------------------------------------------------------------------------
# 200 com JSON na forma errada, ou sem JSON
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_cpopg_listagem_forma_errada_e_json_invalido():
    scraper = _scraper()
    _add_lista(CNJ_1, status=200, json={"content": {"numeroProcesso": CNJ_1}})

    with pytest.warns(UserWarning, match="listagem: json_invalido"):
        df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "status_consulta"] == STATUS_CONSULTA_FALHA
    assert df.loc[0, "motivo_falha"] == "json_invalido"


@responses.activate(registry=OrderedRegistry)
def test_cpopg_detalhes_lista_vazia_e_json_invalido():
    scraper = _scraper()
    numero = _add_lista_tipica(CNJ_1)
    _add_detalhes(numero, status=200, json=[])

    with pytest.warns(UserWarning, match="detalhes: json_invalido"):
        df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "status_consulta"] == STATUS_CONSULTA_FALHA
    assert df.loc[0, "motivo_falha"] == "json_invalido"


@responses.activate(registry=OrderedRegistry)
def test_cpopg_listagem_sem_json_e_retentada_e_vira_json_invalido():
    scraper = _scraper()
    for _ in range(3):
        _add_lista(CNJ_1, status=200, body="<html>manutenção</html>", content_type="text/html")

    with pytest.warns(UserWarning, match="listagem: json_invalido"):
        df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "motivo_falha"] == "json_invalido"
    assert len(responses.calls) == 3


# ---------------------------------------------------------------------------
# Texto e binário dividem a coluna de motivo, com o texto primeiro
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_texto_falho_binario_bom():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), status=404)
    responses.add(responses.GET, _binario_url(UUID_BIN_1), body=b"%PDF", status=200)

    with pytest.warns(UserWarning, match=r"1 download\(s\) de documento falharam.*texto: http_404"):
        df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1, UUID_BIN_1)]))

    assert df.loc[0, "texto"] is None
    assert df.loc[0, "_raw_binary_api"] == b"%PDF"
    assert df.loc[0, "motivo_falha"] == "http_404"


@responses.activate(registry=OrderedRegistry)
def test_binario_falho_texto_bom():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), body="conteúdo", status=200)
    responses.add(responses.GET, _binario_url(UUID_BIN_1), status=403)

    with pytest.warns(UserWarning, match="binario: http_403"):
        df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1, UUID_BIN_1)]))

    assert df.loc[0, "texto"] == "conteúdo"
    assert df.loc[0, "_raw_binary_api"] is None
    assert df.loc[0, "motivo_falha"] == "http_403"


@responses.activate(registry=OrderedRegistry)
def test_texto_e_binario_falhos_motivo_do_texto_e_aviso_com_os_dois():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), status=404)
    responses.add(responses.GET, _binario_url(UUID_BIN_1), status=403)

    with pytest.warns(UserWarning) as avisos:
        df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1, UUID_BIN_1)]))

    mensagem = str(avisos[0].message)
    assert "2 download(s) de documento falharam" in mensagem
    assert "texto: http_404" in mensagem
    assert "binario: http_403" in mensagem
    assert df.loc[0, "motivo_falha"] == "http_404"


@responses.activate(registry=OrderedRegistry)
def test_download_sem_falha_tem_motivo_none_e_nenhum_aviso(recwarn):
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), body="conteúdo", status=200)

    df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))

    assert df.loc[0, "motivo_falha"] is None
    assert not [w for w in recwarn if issubclass(w.category, UserWarning)]


# ---------------------------------------------------------------------------
# 403: uma requisição só
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_cpopg_403_nao_e_retentado():
    scraper = _scraper()
    _add_lista(CNJ_1, status=403, json={"erro": "negado"})

    with pytest.warns(UserWarning, match="listagem: http_403"):
        df = scraper.cpopg(CNJ_1)

    assert len(responses.calls) == 1
    assert df.loc[0, "motivo_falha"] == "http_403"


@responses.activate(registry=OrderedRegistry)
def test_documento_403_nao_e_retentado():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), status=403)

    with pytest.warns(UserWarning, match="texto: http_403"):
        scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))

    assert len(responses.calls) == 1


# ---------------------------------------------------------------------------
# Timeout: retentado, e depois motivo ``timeout``
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_documento_timeout_retentado_e_depois_motivo_timeout():
    scraper = _scraper()
    for _ in range(3):
        responses.add(responses.GET, _texto_url(UUID_TEXT_1), body=requests.ReadTimeout("lento"))

    with pytest.warns(UserWarning, match="texto: timeout"):
        df = scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))

    assert len(responses.calls) == 3
    assert df.loc[0, "motivo_falha"] == "timeout"


@responses.activate(registry=OrderedRegistry)
def test_listagem_timeout_retentado_recupera():
    scraper = _scraper()
    responses.add(responses.GET, LIST_URL, body=requests.ReadTimeout("lento"))
    numero = _add_lista_tipica(CNJ_1)
    _add_detalhes(numero, status=200, body=load_sample("jusbr", "cpopg/typical_single_details.json"))

    df = scraper.cpopg(CNJ_1)

    assert df.loc[0, "motivo_falha"] is None
    assert df.loc[0, "numeroProcesso"] == numero


@responses.activate(registry=OrderedRegistry)
def test_conexao_nao_e_retentada_e_vira_motivo_conexao():
    scraper = _scraper()
    responses.add(responses.GET, LIST_URL, body=requests.ConnectionError("fora do ar"))

    with pytest.warns(UserWarning, match="listagem: conexao"):
        df = scraper.cpopg(CNJ_1)

    assert len(responses.calls) == 1
    assert df.loc[0, "motivo_falha"] == "conexao"


# ---------------------------------------------------------------------------
# Exceção fora do vocabulário propaga
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_cpopg_excecao_fora_do_vocabulario_propaga():
    scraper = _scraper()
    responses.add(responses.GET, LIST_URL, body=requests.TooManyRedirects("laço"))

    with pytest.raises(requests.TooManyRedirects):
        scraper.cpopg(CNJ_1)


@responses.activate(registry=OrderedRegistry)
def test_download_excecao_fora_do_vocabulario_propaga():
    scraper = _scraper()
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), body=requests.TooManyRedirects("laço"))

    with pytest.raises(requests.TooManyRedirects):
        scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))


# ---------------------------------------------------------------------------
# Perfis HTTP
# ---------------------------------------------------------------------------


def test_perfis_declarados():
    perfis = JusbrScraper.perfis_http
    assert set(perfis) == {"listagem", "documento"}
    assert perfis["listagem"].timeout == 15
    assert perfis["documento"].timeout == 30
    for perfil in perfis.values():
        assert perfil.retry_on_timeout is True
        assert perfil.retry_on_connection_error is False
        assert perfil.retryable_statuses == RETRYABLE_STATUSES - {403}
        assert perfil.max_retries == 3
        assert perfil.base_backoff == 2.0


def test_politica_mescla_por_campo():
    scraper = jus.scraper("jusbr", politica={"documento": {"timeout": 10}})
    documento = scraper._perfis_http["documento"]
    assert documento.timeout == 10
    assert documento.retry_on_timeout is True
    assert 403 not in documento.retryable_statuses
    assert scraper._perfis_http["listagem"].timeout == 15


@responses.activate(registry=OrderedRegistry)
def test_politica_chega_ao_documento(mocker):
    scraper = jus.scraper("jusbr", sleep_time=0.0, politica={"documento": {"timeout": 7}})
    scraper.auth(_jwt())
    espiao = mocker.spy(scraper.session, "request")
    responses.add(responses.GET, _texto_url(UUID_TEXT_1), body="x", status=200)

    scraper.download_documents(_base_df([_doc(UUID_TEXT_1)]))

    assert espiao.call_args.kwargs["timeout"] == 7


# ---------------------------------------------------------------------------
# Aviso aponta para quem chamou; pausa também depois de falha
# ---------------------------------------------------------------------------


@responses.activate(registry=OrderedRegistry)
def test_aviso_agregado_aponta_para_quem_chamou():
    scraper = _scraper()
    _add_lista(CNJ_1, status=403, json={"erro": "negado"})

    with pytest.warns(UserWarning) as avisos:
        scraper.cpopg(CNJ_1)

    assert avisos[0].filename == __file__


@responses.activate(registry=OrderedRegistry)
def test_falha_da_listagem_tambem_pausa(mocker):
    scraper = jus.scraper("jusbr", sleep_time=0.25)
    scraper.auth(_jwt())
    pausa = mocker.patch("time.sleep")
    _add_lista(CNJ_1, status=403, json={"erro": "negado"})

    with pytest.warns(UserWarning):
        scraper.cpopg(CNJ_1)

    pausa.assert_called_once_with(0.25)
