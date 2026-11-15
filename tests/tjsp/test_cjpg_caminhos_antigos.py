"""O cjpg passou de ``tjsp/`` para ``_esaj/``; os caminhos antigos continuam importáveis.

Os nomes antigos apontam para os mesmos objetos dos novos: quem importava de
``juscraper.courts.tjsp`` não percebe a mudança.
"""
from juscraper.courts._esaj import cjpg_download as download_esaj
from juscraper.courts._esaj import cjpg_parse as parse_esaj
from juscraper.courts._esaj import schemas as schemas_esaj
from juscraper.courts.tjsp import cjpg_download as download_tjsp
from juscraper.courts.tjsp import cjpg_parse as parse_tjsp
from juscraper.courts.tjsp import schemas as schemas_tjsp
from juscraper.courts.tjsp.exceptions import QueryTooLongError


def test_download_antigo_reexporta_os_mesmos_objetos():
    for nome in ("cjpg_download", "fetch_cjpg_first_page"):
        assert getattr(download_tjsp, nome) is getattr(download_esaj, nome)
    assert download_tjsp.QueryTooLongError is QueryTooLongError


def test_parse_antigo_reexporta_os_mesmos_objetos():
    for nome in parse_tjsp.__all__:
        assert getattr(parse_tjsp, nome) is getattr(parse_esaj, nome)


def test_schemas_antigos_sao_os_do_esaj():
    assert schemas_tjsp.InputCJPGTJSP is schemas_esaj.InputCJPGEsaj
    assert schemas_tjsp.OutputCJPGTJSP is schemas_esaj.OutputCJPGEsaj
