"""Renovacao do access token pelo refresh token, via ``session.auth``."""
import pytest
import requests
import responses

import juscraper as jus
from juscraper.aggregators._pdpj_sso.cache import caminho_cache, carregar_credencial_cache, salvar_credencial
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from juscraper.aggregators._pdpj_sso.renovacao import (
    CLIENT_ID,
    TOKEN_URL,
    RenovacaoPdpjError,
    SsoPdpjIndisponivelError,
    renovar,
)
from juscraper.aggregators.jusbr.download import fetch_document_text
from juscraper.aggregators.pdpj.download import BASE_URL
from tests.pdpj_sso._jwt import token

_EXISTE_URL = f"{BASE_URL}/processos/00000000000000000000/existe"


def _scraper_do_cache(credencial):
    salvar_credencial(credencial)
    return jus.scraper("pdpj", sleep_time=0)


def test_access_vencido_renova_uma_vez_e_regrava_o_cache():
    antigo = CredencialPdpj(token(-60, sub="antigo"), token(3600, sub="refresh"))
    novo_access, novo_refresh = token(sub="novo"), token(7200, sub="refresh-novo")
    scraper = _scraper_do_cache(antigo)
    with responses.RequestsMock() as mocked:
        mocked.post(
            TOKEN_URL,
            json={"access_token": novo_access, "refresh_token": novo_refresh},
            match=[responses.matchers.urlencoded_params_matcher({
                "grant_type": "refresh_token",
                "refresh_token": antigo.refresh_token,
                "client_id": CLIENT_ID,
            })],
        )
        mocked.get(_EXISTE_URL, status=200)
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        scraper.session.get(_EXISTE_URL)
        chamadas_api = [c for c in mocked.calls if c.request.url == _EXISTE_URL]
        assert [c.request.headers["Authorization"] for c in chamadas_api] == [f"Bearer {novo_access}"] * 2
        assert sum(c.request.url == TOKEN_URL for c in mocked.calls) == 1
    assert scraper.token == novo_access
    assert carregar_credencial_cache() == CredencialPdpj(novo_access, novo_refresh)


def test_access_vigente_nao_chama_o_sso():
    credencial = CredencialPdpj(token(3600), token(7200))
    scraper = _scraper_do_cache(credencial)
    with responses.RequestsMock() as mocked:
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[0].request.headers["Authorization"] == f"Bearer {credencial.access_token}"


def test_refresh_recusado_levanta_pedindo_novo_login():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
        with pytest.raises(RuntimeError, match="auth_govbr"):
            scraper.session.get(_EXISTE_URL)


def test_refresh_sem_rotacao_mantem_o_antigo():
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": "novo"})
        assert renovar("refresh-antigo") == CredencialPdpj("novo", "refresh-antigo")


def test_auth_manual_substitui_a_credencial_do_cache():
    scraper = _scraper_do_cache(CredencialPdpj(token(3600, sub="cache"), token(7200)))
    manual = token(sub="manual")
    scraper.auth(manual)
    with responses.RequestsMock() as mocked:
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[0].request.headers["Authorization"] == f"Bearer {manual}"


def test_access_perto_de_vencer_ja_renova():
    """Dentro da margem de renovacao o token ainda vale, mas venceria na requisicao."""
    scraper = _scraper_do_cache(CredencialPdpj(token(10), token(3600)))
    novo = token(sub="novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": novo})
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo}"


def test_recusa_e_memorizada_sem_novo_post():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=400, json={"error": "invalid_grant"})
        for _ in range(3):
            with pytest.raises(RenovacaoPdpjError):
                scraper.session.get(_EXISTE_URL)
        assert len(mocked.calls) == 1


def test_segunda_instancia_aproveita_a_renovacao_da_primeira():
    salvar_credencial(CredencialPdpj(token(-60, sub="antigo"), token(3600, sub="refresh-antigo")))
    jusbr = jus.scraper("jusbr")
    pdpj = jus.scraper("pdpj", sleep_time=0)
    novo_access, novo_refresh = token(sub="novo"), token(7200, sub="refresh-novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": novo_access, "refresh_token": novo_refresh})
        mocked.get(_EXISTE_URL, status=200)
        mocked.get(_EXISTE_URL, status=200)
        jusbr.session.get(_EXISTE_URL)
        pdpj.session.get(_EXISTE_URL)
        assert sum(c.request.url == TOKEN_URL for c in mocked.calls) == 1
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo_access}"
    assert pdpj.token == novo_access


def test_segunda_instancia_renova_com_o_refresh_do_cache():
    """Se o access do cache tambem venceu, o refresh usado e o do cache, nao o da memoria."""
    salvar_credencial(CredencialPdpj(token(-60, sub="a1"), token(3600, sub="r1")))
    pdpj = jus.scraper("pdpj", sleep_time=0)
    refresh_rotacionado = token(3600, sub="r2")
    salvar_credencial(CredencialPdpj(token(-30, sub="a2"), refresh_rotacionado))
    with responses.RequestsMock() as mocked:
        mocked.post(
            TOKEN_URL,
            json={"access_token": token(sub="a3")},
            match=[responses.matchers.urlencoded_params_matcher(
                {"grant_type": "refresh_token", "refresh_token": refresh_rotacionado, "client_id": CLIENT_ID},
            )],
        )
        mocked.get(_EXISTE_URL, status=200)
        pdpj.session.get(_EXISTE_URL)


def test_falha_ao_gravar_o_cache_nao_derruba_a_requisicao(mocker, caplog):
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    mocker.patch("juscraper.aggregators._pdpj_sso.mixin.salvar_credencial", side_effect=PermissionError("sem escrita"))
    novo = token(sub="novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": novo})
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo}"
    assert "Nao foi possivel gravar" in caplog.text


def test_texto_do_jusbr_propaga_a_sessao_encerrada():
    def request_fn(*_args, **_kwargs):
        raise RenovacaoPdpjError("A sessao expirou")

    with pytest.raises(RenovacaoPdpjError):
        fetch_document_text(request_fn, "00000000000000000000", "uuid1", "https://exemplo/")


def test_erro_transitorio_do_sso_nao_e_memorizado():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    novo = token(sub="novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=503)
        mocked.post(TOKEN_URL, json={"access_token": novo})
        mocked.get(_EXISTE_URL, status=200)
        with pytest.raises(SsoPdpjIndisponivelError):
            scraper.session.get(_EXISTE_URL)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo}"


def test_recusa_levanta_excecao_nova_a_cada_requisicao():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    erros = []
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=400)
        for _ in range(2):
            with pytest.raises(RenovacaoPdpjError) as capturado:
                scraper.session.get(_EXISTE_URL)
            erros.append(capturado.value)
    assert erros[0] is not erros[1]


def test_depois_da_recusa_adota_login_novo_gravado_por_outra_instancia():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60, sub="a1"), token(3600, sub="r1")))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=400)
        with pytest.raises(RenovacaoPdpjError):
            scraper.session.get(_EXISTE_URL)
    relogado = CredencialPdpj(token(sub="a2"), token(7200, sub="r2"))
    salvar_credencial(relogado)
    with responses.RequestsMock() as mocked:
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {relogado.access_token}"


def test_refresh_do_cache_recusado_ainda_tenta_o_proprio():
    proprio = token(3600, sub="r-proprio")
    scraper = _scraper_do_cache(CredencialPdpj(token(-60, sub="a1"), proprio))
    antigo = token(3600, sub="r-antigo")
    salvar_credencial(CredencialPdpj(token(-30, sub="a0"), antigo))
    novo = token(sub="novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=400, match=[responses.matchers.urlencoded_params_matcher(
            {"grant_type": "refresh_token", "refresh_token": antigo, "client_id": CLIENT_ID})])
        mocked.post(TOKEN_URL, json={"access_token": novo}, match=[responses.matchers.urlencoded_params_matcher(
            {"grant_type": "refresh_token", "refresh_token": proprio, "client_id": CLIENT_ID})])
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo}"


def test_falha_ao_gravar_desliga_a_leitura_do_cache(mocker):
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    mocker.patch("juscraper.aggregators._pdpj_sso.mixin.salvar_credencial", side_effect=PermissionError("sem escrita"))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": token(sub="novo")})
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
    assert scraper.session.auth.ler_cache is None


def test_sso_fora_do_ar_nao_e_requests_exception():
    """Os downloads tratam RequestException como falha do documento; o SSO precisa escapar disso."""
    assert not issubclass(SsoPdpjIndisponivelError, requests.RequestException)
    assert not issubclass(RenovacaoPdpjError, requests.RequestException)


def test_erro_de_rede_no_sso_vira_indisponivel():
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, body=requests.ConnectionError("sem rede"))
        with pytest.raises(SsoPdpjIndisponivelError):
            renovar("refresh")


def test_sso_fora_do_ar_propaga_no_cpopg_do_jusbr():
    salvar_credencial(CredencialPdpj(token(-60), token(3600)))
    jusbr = jus.scraper("jusbr", sleep_time=0)
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=503)
        with pytest.raises(SsoPdpjIndisponivelError):
            jusbr.cpopg("0000000-00.0000.0.00.0000")


def test_sso_fora_do_ar_propaga_no_cpopg_do_pdpj():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=503)
        with pytest.raises(SsoPdpjIndisponivelError):
            scraper.cpopg("0000000-00.0000.0.00.0000")


def test_texto_do_jusbr_propaga_sso_fora_do_ar():
    def request_fn(*_args, **_kwargs):
        raise SsoPdpjIndisponivelError("fora do ar")

    with pytest.raises(SsoPdpjIndisponivelError):
        fetch_document_text(request_fn, "00000000000000000000", "uuid1", "https://exemplo/")


def test_adotar_do_cache_sem_refresh_preserva_o_proprio():
    proprio = token(3600, sub="r-proprio")
    scraper = _scraper_do_cache(CredencialPdpj(token(-60, sub="a1"), proprio))
    salvar_credencial(CredencialPdpj(token(3600, sub="a2"), None))
    with responses.RequestsMock() as mocked:
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
    assert scraper.session.auth.credencial.refresh_token == proprio


def test_access_do_cache_que_nao_e_jwt_nao_e_adotado():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    caminho_cache().write_text('{"access_token": "lixo-nao-jwt"}', encoding="utf-8")
    novo = token(sub="novo")
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, json={"access_token": novo})
        mocked.get(_EXISTE_URL, status=200)
        scraper.session.get(_EXISTE_URL)
        assert mocked.calls[-1].request.headers["Authorization"] == f"Bearer {novo}"


def test_recusa_final_mantem_o_status_do_sso():
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    with responses.RequestsMock() as mocked:
        mocked.post(TOKEN_URL, status=401)
        with pytest.raises(RenovacaoPdpjError, match="HTTP 401"):
            scraper.session.get(_EXISTE_URL)


def test_gravacao_que_volta_a_funcionar_religa_a_leitura_do_cache(mocker):
    scraper = _scraper_do_cache(CredencialPdpj(token(-60), token(3600)))
    auth = scraper.session.auth
    salvar = mocker.patch("juscraper.aggregators._pdpj_sso.mixin.salvar_credencial", side_effect=PermissionError("x"))
    auth.ao_renovar(CredencialPdpj(token(sub="n1"), token(3600)))
    assert auth.ler_cache is None
    salvar.side_effect = None
    auth.ao_renovar(CredencialPdpj(token(sub="n2"), token(3600)))
    assert auth.ler_cache is not None
