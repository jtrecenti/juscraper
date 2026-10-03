"""Cookie ``aws-waf-token`` do portal de jurisprudencia do STF.

A obtencao vive em :mod:`juscraper.core.waf`, compartilhada com o TJPE; aqui
fica so a pagina que o STF protege e a alternativa sem Playwright (passar um
cookie ja obtido). O cookie vale por cerca de quatro dias.
"""
from __future__ import annotations

from juscraper.core import waf
from juscraper.core.waf import USER_AGENT, WAF_COOKIE

__all__ = ["PAGINA_BUSCA", "USER_AGENT", "WAF_COOKIE", "obter_waf_token"]

PAGINA_BUSCA = "https://jurisprudencia.stf.jus.br/pages/search"


def obter_waf_token(timeout: float = 60.0) -> str:
    """Abre a pagina de busca do STF num Chromium headless e devolve o ``aws-waf-token``.

    Args:
        timeout (float): Segundos de espera pela pagina e pelo cookie. Default ``60``.

    Returns:
        str: Valor do cookie ``aws-waf-token``.

    Raises:
        ImportError: Quando o Playwright nao esta instalado (extra ``juscraper[waf]``).
        RuntimeError: Quando o cookie nao aparece dentro de ``timeout``.
    """
    return waf.obter_waf_token(
        PAGINA_BUSCA,
        timeout,
        tribunal="STF",
        alternativa="Ou passe um cookie ja obtido em `jus.scraper('stf', waf_token=...)`.",
    )
