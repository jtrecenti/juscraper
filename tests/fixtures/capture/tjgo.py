"""Capture cjsg samples for TJGO.

Run from repo root::

    python -m tests.fixtures.capture.tjgo            # amostras com resultado
    python -m tests.fixtures.capture.tjgo turnstile  # resposta bloqueada
    TJGO_JSESSIONID=... python -m tests.fixtures.capture.tjgo atual

Saves raw HTML responses (Projudi) under ``tests/tjgo/samples/cjsg/``.
The Projudi search endpoint requires a GET on the form URL first to
prime session cookies; the POST returns ``iso-8859-1`` encoded HTML.

Desde 12/11/2026 (Projudi 3.194.1) o portal exige o token Cloudflare
Turnstile, e toda busca sem ele volta vazia: ``main`` sobrescreveria as
amostras com resultado por páginas bloqueadas. ``turnstile`` grava só
``blocked_turnstile.html``, a resposta a "dano moral" sem o token.

``atual`` grava ``results_julgado_em_page_01.html`` (HTML atual do portal)
numa sessão que já passou pelo Turnstile. Faça uma busca no navegador,
resolva o widget e copie o cookie ``JSESSIONID`` de projudi.tjgo.jus.br para
``TJGO_JSESSIONID``: uma sessão autorizada aceita buscas sem token. O
balanceador do Projudi escolhe o servidor pelo cookie ``WIDPROP``, e sem ele
a requisição cai noutro servidor, que abre outra sessão; o script deriva o
``WIDPROP`` do sufixo ``:server-<id>`` do ``JSESSIONID``. Se a resposta
vier sem resultados, o script para sem gravar.
"""
import logging
import os
import re
import sys

import requests

from juscraper.courts.tjgo.client import TJGOScraper
from juscraper.courts.tjgo.download import SEARCH_URL, build_cjsg_payload
from juscraper.courts.tjgo.parse import has_results

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

USER_AGENT = TJGOScraper.USER_AGENT
COOKIE_DOMAIN = "projudi.tjgo.jus.br"
# ``JSESSIONID=<id>.cp09:server-cp09-1`` vem com ``WIDPROP=.cp09-1``.
_SERVIDOR_RE = re.compile(r":server-([\w-]+)$")


def _post(session: requests.Session, pesquisa: str, page: int) -> bytes:
    body = build_cjsg_payload(pesquisa=pesquisa, page=page)
    response = session.post(SEARCH_URL, data=body, timeout=90)
    response.raise_for_status()
    return response.content


def _capture(session: requests.Session, dest, pesquisa: str, page: int, filename: str) -> None:
    content = _post(session, pesquisa, page)
    dump(dest / filename, content)
    logger.info("[tjgo] wrote %s (page=%s, bytes=%s)", filename, page, len(content))


def _session(jsessionid: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    if jsessionid:
        servidor = _SERVIDOR_RE.search(jsessionid)
        if servidor is None:
            raise SystemExit(
                "[tjgo] TJGO_JSESSIONID sem o sufixo ':server-<id>'; copie o valor inteiro do cookie."
            )
        session.cookies.set("JSESSIONID", jsessionid, domain=COOKIE_DOMAIN, path="/")
        session.cookies.set("WIDPROP", f".{servidor.group(1)}", domain=COOKIE_DOMAIN, path="/")
    # Prime cookies — Projudi requires the GET before the POST.
    session.get(SEARCH_URL, timeout=60)
    return session


def capture_turnstile() -> None:
    """Capture the response to a search sent without the Turnstile token."""
    _capture(_session(), samples_dir_for("tjgo", "cjsg"), "dano moral", 1, "blocked_turnstile.html")


def capture_atual() -> None:
    """Capture the current portal HTML using a session already past Turnstile."""
    jsessionid = os.environ.get("TJGO_JSESSIONID", "").strip().strip("\"'")
    if not jsessionid:
        raise SystemExit("[tjgo] defina TJGO_JSESSIONID com o cookie de uma sessão autorizada.")
    session = _session(jsessionid)
    # Uma sessão expirada volta com outro JSESSIONID no Set-Cookie do GET.
    if any(c.name == "JSESSIONID" and c.value != jsessionid for c in session.cookies):
        raise SystemExit("[tjgo] o portal abriu outra sessão: a de TJGO_JSESSIONID expirou.")
    content = _post(session, "dano moral", 1)
    if not has_results(content.decode("iso-8859-1")):
        raise SystemExit(
            "[tjgo] a busca voltou sem resultados: a sessão não passou pelo Turnstile. "
            "Nada foi gravado."
        )
    filename = "results_julgado_em_page_01.html"
    dump(samples_dir_for("tjgo", "cjsg") / filename, content)
    logger.info("[tjgo] wrote %s (page=1, bytes=%s)", filename, len(content))


def main() -> None:
    """Capture cjsg HTML samples for TJGO."""
    dest = samples_dir_for("tjgo", "cjsg")
    session = _session()

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.html")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.html")
    _capture(session, dest, "usucapiao extraordinario predio rural familia", 1, "single_page.html")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.html")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if sys.argv[1:] == ["turnstile"]:
        capture_turnstile()
    elif sys.argv[1:] == ["atual"]:
        capture_atual()
    else:
        main()
