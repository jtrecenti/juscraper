"""Obtencao do cookie ``aws-waf-token`` de portais atras do AWS WAF.

O AWS WAF responde a requisicoes sem o cookie ``aws-waf-token`` com HTTP 202 e
um desafio JavaScript. O desafio so se resolve executando JavaScript, entao o
token sai de um Chromium controlado pelo Playwright (extra ``juscraper[waf]``);
depois disso as requisicoes seguem em ``requests`` com o cookie.

O user agent precisa ser o de um Chrome comum: o WAF responde 403, antes mesmo de
oferecer o desafio, ao ``HeadlessChrome`` que o Playwright anuncia por padrao. A
sessao ``requests`` usa o mesmo :data:`USER_AGENT` do navegador que obteve o
token, porque o WAF amarra o cookie ao user agent.

Usado pelo STF (jurisprudencia) e pelo TJPE (consulta publica do PJe).
"""
from __future__ import annotations

import time
from concurrent import futures

import requests

WAF_COOKIE = "aws-waf-token"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
)

# Marcadores da pagina de desafio que o WAF serve no corpo do 202. O cabecalho
# ``x-amzn-waf-action`` e o sinal documentado; o corpo cobre a resposta que chega
# sem ele, como a que o TJPE devolveu no lugar do formulario da consulta publica.
_MARCADORES_DESAFIO = (b"gokuProps", b"awsWafCookieDomainList")


def eh_desafio_waf(resp: requests.Response) -> bool:
    """Diz se ``resp`` e o desafio JavaScript do AWS WAF, e nao a pagina pedida."""
    if resp.headers.get("x-amzn-waf-action") == "challenge":
        return True
    if resp.status_code != 202:
        return False
    inicio = resp.content[:4096]
    return any(marcador in inicio for marcador in _MARCADORES_DESAFIO)


def obter_waf_token(
    pagina: str,
    timeout: float = 60.0,
    *,
    tribunal: str,
    alternativa: str = "",
) -> str:
    """Abre ``pagina`` num Chromium headless e devolve o ``aws-waf-token``.

    Args:
        pagina (str): URL que o WAF protege; o desafio roda ao carrega-la.
        timeout (float): Segundos de espera pela pagina e pelo cookie. Default ``60``.
        tribunal (str): Nome usado nas mensagens de erro (ex.: ``"STF"``).
        alternativa (str): Frase acrescentada ao ``ImportError`` para indicar
            outro caminho sem Playwright (ex.: passar um cookie ja obtido).

    Returns:
        str: Valor do cookie ``aws-waf-token``.

    Raises:
        ImportError: Quando o Playwright nao esta instalado (extra ``juscraper[waf]``).
        RuntimeError: Quando o cookie nao aparece dentro de ``timeout``.
    """
    # O Playwright síncrono exige uma thread sem o loop ativo do Jupyter.
    with futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_obtain_waf_token, pagina, timeout, tribunal, alternativa).result()


def _obtain_waf_token(pagina: str, timeout: float, tribunal: str, alternativa: str) -> str:
    try:
        from playwright.sync_api import sync_playwright  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        mensagem = (
            f"O raspador do {tribunal} precisa do Playwright para obter o cookie {WAF_COOKIE}. "
            "Instale com `pip install 'juscraper[waf]'` seguido de `playwright install chromium`."
        )
        if alternativa:
            mensagem = f"{mensagem} {alternativa}"
        raise ImportError(mensagem) from exc

    with sync_playwright() as pw:
        # channel="chromium" usa o headless novo do Chromium, que resolve o desafio;
        # o chromium-headless-shell padrao do Playwright recebe 403.
        browser = pw.chromium.launch(headless=True, channel="chromium")
        try:
            context = browser.new_context(user_agent=USER_AGENT, locale="pt-BR")
            page = context.new_page()
            page.goto(pagina, wait_until="domcontentloaded", timeout=timeout * 1000)
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
        f"O portal do {tribunal} nao emitiu o cookie {WAF_COOKIE} em {timeout:.0f}s. "
        "O desafio do WAF pode ter mudado ou exigido interacao."
    )
