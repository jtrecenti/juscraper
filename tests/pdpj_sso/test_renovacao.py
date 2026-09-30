"""Renovacao do access token pelo refresh token, via ``session.auth``."""
import pytest
import responses

import juscraper as jus
from juscraper.aggregators._pdpj_sso.cache import carregar_credencial_cache, salvar_credencial
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from juscraper.aggregators._pdpj_sso.renovacao import CLIENT_ID, TOKEN_URL, renovar
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
