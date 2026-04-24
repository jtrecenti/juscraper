"""Capture cjsg samples for TJPI.

Run from repo root::

    python -m tests.fixtures.capture.tjpi

Saves raw HTML responses under ``tests/tjpi/samples/cjsg/``. TJPI uses
a GET with query-string parameters and has no filters for date ranges.
``single_page`` must contain zero pagination links for the
``_get_total_pages`` regex fallback to return 1.
"""
import requests

from juscraper.courts.tjpi.download import BASE_URL, build_cjsg_params

from ._util import dump, samples_dir_for


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    params = build_cjsg_params(pesquisa, page=pagina)
    response = session.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    dump(dest / filename, response.content)
    print(f"[tjpi] wrote {filename}")


def main() -> None:
    """Capture cjsg HTML samples for TJPI."""
    dest = samples_dir_for("tjpi", "cjsg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
    })

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.html")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.html")
    _capture(session, dest, "mandado de seguranca usucapiao extraordinario", 1, "single_page.html")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.html")


if __name__ == "__main__":
    main()
