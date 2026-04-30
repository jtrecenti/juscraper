"""Capture cjsg samples for TJGO.

Run from repo root::

    python -m tests.fixtures.capture.tjgo

Saves raw HTML responses (Projudi) under ``tests/tjgo/samples/cjsg/``.
The Projudi search endpoint requires a GET on the form URL first to
prime session cookies; the POST returns ``iso-8859-1`` encoded HTML.
"""
import requests

from juscraper.courts.tjgo.download import SEARCH_URL, build_cjsg_payload

from ._util import dump, samples_dir_for

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


def _capture(session: requests.Session, dest, pesquisa: str, page: int, filename: str) -> None:
    body = build_cjsg_payload(pesquisa=pesquisa, page=page)
    response = session.post(SEARCH_URL, data=body, timeout=90)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjgo] wrote {filename} (page={page}, bytes={len(response.content)})")


def main() -> None:
    """Capture cjsg HTML samples for TJGO."""
    dest = samples_dir_for("tjgo", "cjsg")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    # Prime cookies — Projudi requires the GET before the POST.
    session.get(SEARCH_URL, timeout=60)

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.html")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.html")
    _capture(session, dest, "usucapiao extraordinario predio rural familia", 1, "single_page.html")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.html")


if __name__ == "__main__":
    main()
