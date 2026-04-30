"""Capture cjsg + cjpg samples for TJTO.

Run from repo root::

    python -m tests.fixtures.capture.tjto

Saves the Solr-style HTML responses for each public method (cjsg, cjpg)
plus two ``ementa_<uuid>.json`` payloads from the ``ementa.php`` endpoint
that powers ``cjsg_ementa(uuid)``.
"""
import re

import requests
from bs4 import BeautifulSoup

from juscraper.courts.tjto.download import BASE_URL, EMENTA_URL, build_cjsg_payload

from ._util import dump, samples_dir_for

USER_AGENT = "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"
_UUID_RE = re.compile(r'data-id="([a-f0-9-]{30,})"')


def _minify(raw: bytes) -> bytes:
    """Keep only the ``#result`` block (panel-document + total-results tab).

    The full TJTO response is ~1 MB per page; the parser only consumes the
    ``#result`` div (137 KB). The lateral filter sidebar is the bulk of the
    weight and isn't read by either ``_get_total_results`` or
    ``cjsg_parse_manager`` — drop it.
    """
    soup = BeautifulSoup(raw, "html.parser")
    result = soup.select_one("#result")
    if result is None:
        return raw  # nothing to strip — defensive
    return f"<html><body>{result}</body></html>".encode("utf-8")


def _post(session: requests.Session, query: str, *, start: int, instancia: str) -> requests.Response:
    payload = build_cjsg_payload(query, start=start, tip_criterio_inst=instancia)
    response = session.post(BASE_URL, data=payload, timeout=60)
    response.raise_for_status()
    return response


def _capture_endpoint(session: requests.Session, dest, endpoint: str,
                      instancia: str, queries: list) -> None:
    out = samples_dir_for("tjto", endpoint)
    for query, pages, files in queries:
        for page, filename in zip(pages, files):
            start = (page - 1) * 20
            response = _post(session, query, start=start, instancia=instancia)
            stripped = _minify(response.content)
            dump(out / filename, stripped)
            print(f"[tjto/{endpoint}] wrote {filename} (page={page}, "
                  f"raw={len(response.content)}, minified={len(stripped)})")


def _capture_ementas(session: requests.Session, sample_path) -> None:
    """Capture two ``_fetch_ementa`` payloads from UUIDs in the typical sample."""
    html = sample_path.read_bytes().decode("utf-8", errors="replace")
    uuids = _UUID_RE.findall(html)
    seen: set = set()
    out = samples_dir_for("tjto", "cjsg")
    for uuid in uuids:
        if uuid in seen:
            continue
        seen.add(uuid)
        if len(seen) > 2:
            break
        response = session.get(EMENTA_URL, params={"id": uuid}, timeout=30)
        response.raise_for_status()
        filename = f"ementa_{uuid}.json"
        dump(out / filename, response.content)
        print(f"[tjto/cjsg] wrote {filename} (bytes={len(response.content)})")


def main() -> None:
    """Capture cjsg + cjpg + ementa samples for TJTO."""
    cjsg_dest = samples_dir_for("tjto", "cjsg")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    cjsg_queries = [
        ("dano moral", (1, 2),
         ("results_normal_page_01.html", "results_normal_page_02.html")),
        ("\"alimentos avoengos\"", (1,), ("single_page.html",)),
        ("juscraper_probe_zero_hits_xyzqwe", (1,), ("no_results.html",)),
    ]
    _capture_endpoint(session, cjsg_dest, "cjsg", instancia="2",
                      queries=cjsg_queries)

    cjpg_dest = samples_dir_for("tjto", "cjpg")
    cjpg_queries = [
        ("\"dano moral\"", (1, 2),
         ("results_normal_page_01.html", "results_normal_page_02.html")),
        ("\"despejo\"", (1,), ("single_page.html",)),
        ("juscraper_probe_zero_hits_xyzqwe", (1,), ("no_results.html",)),
    ]
    _capture_endpoint(session, cjpg_dest, "cjpg", instancia="1",
                      queries=cjpg_queries)

    _capture_ementas(session, cjsg_dest / "results_normal_page_01.html")


if __name__ == "__main__":
    main()
