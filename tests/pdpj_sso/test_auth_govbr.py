"""``auth_govbr()`` nos dois scrapers, com o login do navegador substituido."""
import logging

import pytest

import juscraper as jus
from juscraper.aggregators._pdpj_sso.cache import caminho_cache, carregar_credencial_cache
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from tests.pdpj_sso._jwt import token

_LOGIN = "juscraper.aggregators._pdpj_sso.mixin.obter_credencial_govbr"


@pytest.fixture(params=["jusbr", "pdpj"])
def scraper(request):
    return jus.scraper(request.param)


def test_instala_a_credencial_com_renovacao_e_grava_o_cache(mocker, scraper):
    credencial = CredencialPdpj(token(), token(7200))
    login = mocker.patch(_LOGIN, return_value=credencial)

    assert scraper.auth_govbr(timeout=60) is True

    login.assert_called_once_with(timeout=60, navegador=None)
    assert scraper.token == credencial.access_token
    assert scraper.session.auth.credencial == credencial
    assert carregar_credencial_cache() == credencial


def test_salvar_false_nao_grava(mocker, scraper):
    mocker.patch(_LOGIN, return_value=CredencialPdpj(token(), token(7200)))

    scraper.auth_govbr(salvar=False)

    assert not caminho_cache().exists()


def test_sem_refresh_avisa(mocker, scraper, caplog):
    mocker.patch(_LOGIN, return_value=CredencialPdpj(token()))

    with caplog.at_level(logging.WARNING):
        scraper.auth_govbr()

    assert "refresh token" in caplog.text


def test_access_vencido_vindo_do_login_e_recusado(mocker, scraper):
    mocker.patch(_LOGIN, return_value=CredencialPdpj(token(-60), token(7200)))

    with pytest.raises(ValueError, match="expirado"):
        scraper.auth_govbr()

    assert scraper.token is None
    assert not caminho_cache().exists()


def test_kwarg_desconhecido_levanta_type_error(mocker, scraper):
    login = mocker.patch(_LOGIN)

    with pytest.raises(TypeError, match="parametro_inexistente"):
        scraper.auth_govbr(parametro_inexistente=1)

    login.assert_not_called()


def test_timeout_nao_positivo_e_recusado(mocker, scraper):
    mocker.patch(_LOGIN)

    with pytest.raises(ValueError, match="timeout"):
        scraper.auth_govbr(timeout=0)


def test_proxima_instancia_carrega_do_cache(mocker, scraper):
    credencial = CredencialPdpj(token(), token(7200))
    mocker.patch(_LOGIN, return_value=credencial)
    scraper.auth_govbr()

    assert jus.scraper("jusbr").token == credencial.access_token
    assert jus.scraper("pdpj").token == credencial.access_token


@pytest.mark.parametrize("nome", ["jusbr", "pdpj"])
def test_sem_auth_a_mensagem_cita_auth_govbr(nome):
    scraper = jus.scraper(nome)
    with pytest.raises(RuntimeError, match="auth_govbr"):
        scraper.cpopg("0000000-00.0000.0.00.0000")


def test_salvar_false_tambem_nao_grava_as_renovacoes(mocker, scraper):
    mocker.patch(_LOGIN, return_value=CredencialPdpj(token(), token(7200)))
    scraper.auth_govbr(salvar=False)

    assert scraper.session.auth.ler_cache is None
    scraper.session.auth.ao_renovar(CredencialPdpj(token(sub="renovado"), token(7200)))

    assert not caminho_cache().exists()


def test_falha_ao_gravar_o_cache_nao_derruba_o_login(mocker, scraper, caplog):
    credencial = CredencialPdpj(token(), token(7200))
    mocker.patch(_LOGIN, return_value=credencial)
    mocker.patch("juscraper.aggregators._pdpj_sso.mixin.salvar_credencial", side_effect=PermissionError("sem escrita"))

    assert scraper.auth_govbr() is True
    assert scraper.token == credencial.access_token
    assert "Nao foi possivel gravar" in caplog.text


def test_login_com_falha_ao_gravar_nao_le_cache_antigo(mocker, scraper):
    mocker.patch(_LOGIN, return_value=CredencialPdpj(token(), token(7200)))
    mocker.patch("juscraper.aggregators._pdpj_sso.mixin.salvar_credencial", side_effect=PermissionError("sem escrita"))

    scraper.auth_govbr()

    assert scraper.session.auth.ler_cache is None
