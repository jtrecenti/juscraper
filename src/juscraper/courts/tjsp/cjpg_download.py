"""Caminho antigo do download do cjpg, que passou para :mod:`juscraper.courts._esaj.cjpg_download`.

O cjpg é do eSAJ, comum a TJSP e TJMS. Este módulo só reexporta os nomes
públicos, para quem os importava daqui.
"""
from .._esaj.cjpg_download import cjpg_download, fetch_cjpg_first_page
from .exceptions import QueryTooLongError

__all__ = ["QueryTooLongError", "cjpg_download", "fetch_cjpg_first_page"]
