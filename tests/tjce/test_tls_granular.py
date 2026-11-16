"""Adaptador TLS do TJCE: o servidor só fecha o handshake com ``SECLEVEL=1``."""
import ssl

import juscraper as jus
from juscraper.courts.tjce._tls import _TJCETLSAdapter
from juscraper.courts.tjce.cjsg_download import _TJCETLSAdapter as _AdaptadorPeloCaminhoAntigo


def test_contexto_ssl_usa_seclevel_1():
    ctx = _TJCETLSAdapter().poolmanager.connection_pool_kw["ssl_context"]

    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.security_level == 1
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_sessao_do_tjce_monta_o_adaptador_em_https():
    session = jus.scraper("tjce").session

    assert isinstance(session.get_adapter("https://esaj.tjce.jus.br/cjsg/"), _TJCETLSAdapter)
    assert not isinstance(session.get_adapter("http://esaj.tjce.jus.br/"), _TJCETLSAdapter)


def test_caminho_antigo_reexporta_o_mesmo_adaptador():
    assert _AdaptadorPeloCaminhoAntigo is _TJCETLSAdapter
