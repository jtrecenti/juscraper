"""Capture cjsg and cjpg samples for TJMS.

Run from repo root, from a residential IP (``esaj.tjms.jus.br`` does not
answer datacenter IPs)::

    python -m tests.fixtures.capture.tjms
"""
import json
import time

from bs4 import BeautifulSoup

from ._util import build_session, capture_cjsg_samples, dump, make_tjsp_cjpg_params, samples_dir_for

ESAJ_BASE = "https://esaj.tjms.jus.br/"


def capture_cjpg() -> None:
    """Capture cjpg samples and the pasta behind the first sentence.

    Saves under ``tests/tjms/samples/cjpg/``: two pages of ``dano moral``,
    a search with no hits, and, for the first result of page 1, the
    ``Location`` of ``cjpg/obterArquivo.do`` (``redirecionamentos.json``)
    and the pasta digital page it leads to. The PDF itself is not saved:
    the tests only need a body starting with ``%PDF``.
    """
    dest = samples_dir_for("tjms", "cjpg")

    session = build_session()
    session.get(f"{ESAJ_BASE}cjpg/open.do", timeout=60)
    r1 = session.get(f"{ESAJ_BASE}cjpg/pesquisar.do", params=make_tjsp_cjpg_params("dano moral"), timeout=60)
    r1.raise_for_status()
    dump(dest / "results_normal_page_01.html", r1.content)
    time.sleep(1.5)
    r2 = session.get(f"{ESAJ_BASE}cjpg/trocarDePagina.do", params={"pagina": "2", "conversationId": ""}, timeout=60)
    r2.raise_for_status()
    dump(dest / "results_normal_page_02.html", r2.content)

    time.sleep(1.5)
    session = build_session()
    r_none = session.get(
        f"{ESAJ_BASE}cjpg/pesquisar.do",
        params=make_tjsp_cjpg_params("juscraper_probe_zero_hits_xyzqwe"),
        timeout=60,
    )
    r_none.raise_for_status()
    dump(dest / "no_results.html", r_none.content)

    link = BeautifulSoup(r1.content, "html.parser").find("a", {"style": "vertical-align: top"})
    if link is None or not link.get("name"):
        raise RuntimeError("cjpg: primeira sentença sem atributo name")
    cd_processo, cd_foro, nm_alias, cd_documento = str(link["name"]).split("-")
    time.sleep(1.5)
    resposta = session.get(
        f"{ESAJ_BASE}cjpg/obterArquivo.do",
        params={"cdProcesso": cd_processo, "cdForo": cd_foro, "nmAlias": nm_alias, "cdDocumento": cd_documento},
        allow_redirects=False,
        timeout=60,
    )
    if resposta.status_code != 302:
        raise RuntimeError(f"obterArquivo.do: esperava 302, veio {resposta.status_code}")
    local = resposta.headers["Location"]
    time.sleep(1.5)
    dump(dest / f"pasta_{cd_documento}.html", session.get(local, timeout=60).content)
    dump(dest / "redirecionamentos.json", json.dumps({f"sentenca_{cd_documento}": local}, indent=1).encode())


def main() -> None:
    """Capture cjsg and cjpg samples for TJMS."""
    capture_cjsg_samples(
        tribunal="tjms",
        base_url="https://esaj.tjms.jus.br/",
    )
    capture_cjpg()


if __name__ == "__main__":
    main()
