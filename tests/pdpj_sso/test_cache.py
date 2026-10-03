"""Cache local da credencial e ordem de busca da credencial padrao."""
import logging
import sys

import pytest

import juscraper as jus
from juscraper.aggregators._pdpj_sso.cache import (
    caminho_cache,
    carregar_credencial_cache,
    carregar_credencial_padrao,
    salvar_credencial,
)
from juscraper.aggregators._pdpj_sso.credencial import CredencialPdpj
from tests.pdpj_sso._jwt import token


def test_caminho_segue_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert caminho_cache() == tmp_path / "juscraper" / "pdpj_token.json"


def test_ida_e_volta_preserva_os_dois_tokens():
    credencial = CredencialPdpj(token(), token(7200))
    salvar_credencial(credencial)
    assert carregar_credencial_cache() == credencial


@pytest.mark.skipif(sys.platform == "win32", reason="permissao POSIX")
def test_arquivo_legivel_so_pelo_dono():
    caminho = salvar_credencial(CredencialPdpj(token()))
    assert caminho.stat().st_mode & 0o777 == 0o600
    assert caminho.parent.stat().st_mode & 0o777 == 0o700


@pytest.mark.parametrize("conteudo", ["{nao e json", "[]", '{"refresh_token": "x"}'])
def test_cache_corrompido_vira_none(conteudo):
    caminho = caminho_cache()
    caminho.parent.mkdir(parents=True)
    caminho.write_text(conteudo, encoding="utf-8")
    assert carregar_credencial_cache() is None


def test_sem_cache_nem_ambiente_nada_e_carregado():
    assert carregar_credencial_padrao(("PDPJ_JWT",)) is None
    scraper = jus.scraper("pdpj")
    assert scraper.token is None
    assert scraper.session.auth is None


def test_precedencia_token_explicito_vence_ambiente_e_cache(monkeypatch):
    explicito, do_env, do_cache = token(sub="explicito"), token(sub="env"), token(sub="cache")
    monkeypatch.setenv("PDPJ_JWT", do_env)
    salvar_credencial(CredencialPdpj(do_cache))
    assert jus.scraper("jusbr", token=explicito).token == explicito
    assert jus.scraper("pdpj", token=explicito).token == explicito


def test_precedencia_pdpj_jwt_antes_de_jusbr_jwt_antes_do_cache(monkeypatch):
    pdpj, jusbr, cache = token(sub="pdpj"), token(sub="jusbr"), token(sub="cache")
    salvar_credencial(CredencialPdpj(cache))
    assert jus.scraper("jusbr").token == cache
    monkeypatch.setenv("JUSBR_JWT", jusbr)
    assert jus.scraper("jusbr").token == jusbr
    monkeypatch.setenv("PDPJ_JWT", pdpj)
    assert jus.scraper("jusbr").token == pdpj


def test_pdpj_nao_le_jusbr_jwt(monkeypatch):
    monkeypatch.setenv("JUSBR_JWT", token())
    assert jus.scraper("pdpj").token is None


def test_candidato_vencido_e_ignorado_com_aviso_sem_o_token(monkeypatch, caplog):
    vencido = token(-60, sub="segredo-vencido")
    do_cache = token(sub="cache")
    monkeypatch.setenv("PDPJ_JWT", vencido)
    salvar_credencial(CredencialPdpj(do_cache))
    with caplog.at_level(logging.WARNING):
        scraper = jus.scraper("pdpj")
    assert scraper.token == do_cache
    assert "PDPJ_JWT" in caplog.text
    assert vencido not in caplog.text


def test_access_vencido_com_refresh_vigente_e_carregado():
    credencial = CredencialPdpj(token(-60), token(3600))
    salvar_credencial(credencial)
    scraper = jus.scraper("jusbr")
    assert scraper.token == credencial.access_token
    assert scraper.session.auth.credencial == credencial


def test_access_vencido_sem_refresh_vigente_nao_e_carregado():
    salvar_credencial(CredencialPdpj(token(-60), token(-10)))
    assert jus.scraper("jusbr").token is None


def test_access_malformado_nao_e_carregado(monkeypatch):
    monkeypatch.setenv("PDPJ_JWT", "nao-e-jwt")
    assert jus.scraper("pdpj").token is None


def test_repr_nao_mostra_os_tokens():
    credencial = CredencialPdpj("ACCESS-SECRETO", "REFRESH-SECRETO")
    assert "SECRETO" not in repr(credencial)


def test_gravacao_que_falha_apaga_o_temporario_e_preserva_o_cache(mocker):
    anterior = CredencialPdpj(token(), token(7200))
    salvar_credencial(anterior)
    mocker.patch("juscraper.aggregators._pdpj_sso.cache.json.dump", side_effect=OSError("disco cheio"))

    with pytest.raises(OSError, match="disco cheio"):
        salvar_credencial(CredencialPdpj(token(60)))

    assert [p.name for p in caminho_cache().parent.iterdir()] == ["pdpj_token.json"]
    assert carregar_credencial_cache() == anterior
