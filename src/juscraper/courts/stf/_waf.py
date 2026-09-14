"""Obtencao do cookie ``aws-waf-token`` do portal de jurisprudencia do STF.

O portal fica atras do AWS WAF, que responde a requisicoes sem o cookie
``aws-waf-token`` com HTTP 202 e um desafio JavaScript. O desafio so se resolve
executando JavaScript, entao o token sai de um Chromium controlado pelo
Playwright; depois disso as buscas seguem em ``requests`` com o cookie, que vale
por cerca de quatro dias.

O user agent precisa ser o de um Chrome comum: o WAF responde 403, antes mesmo de
oferecer o desafio, ao ``HeadlessChrome`` que o Playwright anuncia por padrao. A
sessao ``requests`` usa o mesmo user agent do navegador que obteve o token.
"""
from __future__ import annotations

import time

PAGINA_BUSCA = "https://jurisprudencia.stf.jus.br/pages/search"
WAF_COOKIE = "aws-waf-token"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)


def obter_waf_token(timeout: float = 60.0) -> str:
    """Abre a pagina de busca num Chromium headless e devolve o ``aws-waf-token``.

    Args:
        timeout (float): Segundos de espera pela pagina e pelo cookie. Default ``60``.

    Returns:
        str: Valor do cookie ``aws-waf-token``.

    Raises:
        ImportError: Quando o Playwright nao esta instalado (extra ``juscraper[stf]``).
        RuntimeError: Quando o cookie nao aparece dentro de ``timeout``.
    """
    try:
        from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "O raspador do STF precisa do Playwright para obter o cookie aws-waf-token. "
            "Instale com `pip install 'juscraper[stf]'` seguido de `playwright install chromium`, "
            "ou passe um cookie ja obtido em `jus.scraper('stf', waf_token=...)`."
        ) from exc

    with sync_playwright() as pw:
        # channel="chromium" usa o headless novo do Chromium, que resolve o desafio;
        # o chromium-headless-shell padrao do Playwright recebe 403.
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="pt-BR")
            page = context.new_page()
            page.goto(PAGINA_BUSCA, wait_until="domcontentloaded", timeout=timeout * 1000)
            prazo = time.monotonic() + timeout
            while time.monotonic() < prazo:
                for cookie in context.cookies():
                    if cookie["name"] == WAF_COOKIE:
                        token: str = cookie["value"]
                        return token
                page.wait_for_timeout(500)
        finally:
            browser.close()
    raise RuntimeError(
        f"O portal do STF nao emitiu o cookie {WAF_COOKIE} em {timeout:.0f}s. "
        "O desafio do WAF pode ter mudado ou exigido interacao."
    )
