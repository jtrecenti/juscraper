"""Caminho antigo do parse do cjpg, que passou para :mod:`juscraper.courts._esaj.cjpg_parse`.

O cjpg é do eSAJ, comum a TJSP e TJMS. Este módulo só reexporta os nomes
públicos, para quem os importava daqui.
"""
from .._esaj.cjpg_parse import (
    MARCA_PAGINA_NAO_BAIXADA,
    cjpg_n_pags,
    cjpg_n_results,
    cjpg_parse_manager,
    cjpg_parse_single,
)

__all__ = [
    "MARCA_PAGINA_NAO_BAIXADA",
    "cjpg_n_pags",
    "cjpg_n_results",
    "cjpg_parse_manager",
    "cjpg_parse_single",
]
