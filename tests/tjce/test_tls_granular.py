"""Adaptador TLS do TJCE: o servidor só fecha o handshake com ``SECLEVEL=1``."""
import ssl

import pytest

import juscraper as jus
from juscraper.courts.tjce import _tls
from juscraper.courts.tjce._tls import _TJCETLSAdapter
from juscraper.courts.tjce.cjsg_download import _TJCETLSAdapter as _AdaptadorPeloCaminhoAntigo


@pytest.mark.parametrize(
    "manager",
    [
        pytest.param(lambda adapter: adapter.poolmanager, id="direto"),
        pytest.param(lambda adapter: adapter.proxy_manager_for("http://proxy.example:3128"), id="proxy"),
    ],
)
def test_contexto_ssl_usa_seclevel_1(manager):
    ctx = manager(_TJCETLSAdapter()).connection_pool_kw["ssl_context"]

    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.security_level == 1
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_proxy_reaproveita_o_manager_e_o_contexto(mocker):
    adapter = _TJCETLSAdapter()
    cria_contexto = mocker.spy(_tls, "_contexto_ssl")

    manager = adapter.proxy_manager_for("http://proxy.example:3128")

    assert adapter.proxy_manager_for("http://proxy.example:3128") is manager
    cria_contexto.assert_called_once_with()


def test_sessao_do_tjce_monta_o_adaptador_em_https():
    session = jus.scraper("tjce").session

    assert isinstance(session.get_adapter("https://esaj.tjce.jus.br/cjsg/"), _TJCETLSAdapter)
    assert not isinstance(session.get_adapter("http://esaj.tjce.jus.br/"), _TJCETLSAdapter)


def test_caminho_antigo_reexporta_o_mesmo_adaptador():
    assert _AdaptadorPeloCaminhoAntigo is _TJCETLSAdapter
