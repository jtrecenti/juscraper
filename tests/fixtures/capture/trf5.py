"""Capture cpopg samples for TRF5 against the live PJe deployment.

Run from repo root::

    python -m tests.fixtures.capture.trf5

Writes ``form_initial.html``, ``search_one_result.html``,
``search_no_results.html`` and ``detail_normal.html`` to
``tests/trf5/samples/cpopg/``.

Goes through the *real* scraper helpers in
:mod:`juscraper.courts.trf5.download` — using the same payload-builder and
field-extraction code as the production code path, so any drift between the
scraper and what the live tribunal actually accepts breaks this script first
(instead of silently producing stale samples).
"""
from __future__ import annotations

from pathlib import Path

import juscraper as jus
from juscraper.courts.trf5.download import (
    build_search_payload,
    extract_ca_token,
    extract_form_field_ids,
    fetch_detail,
    fetch_form,
    submit_search,
)
from juscraper.utils.cnj import clean_cnj, format_cnj

REPO_ROOT = Path(__file__).resolve().parents[3]

# Single-result CNJ taken from data/amostra_jf_primeiro_grau.csv —
# CEJUSC Maceió (AL).
FOUND_CNJ = "00584573120254058000"

# Synthetic CNJ shaped like a TRF5 process so the form mask validation passes;
# backend returns an empty Ajax fragment with no ca token.
MISSING_CNJ = "00000000020994050000"


def main() -> None:
    """Capture cpopg samples for TRF5."""
    dest = REPO_ROOT / "tests" / "trf5" / "samples" / "cpopg"
    dest.mkdir(parents=True, exist_ok=True)
    scraper = jus.scraper("trf5", sleep_time=0.5)

    form_html = fetch_form(scraper.session)
    (dest / "form_initial.html").write_text(form_html, encoding="utf-8")
    field_ids = extract_form_field_ids(form_html)
    print(f"[trf5] field ids: {field_ids}")

    found_payload = build_search_payload(format_cnj(clean_cnj(FOUND_CNJ)), field_ids)
    found_html = submit_search(scraper.session, found_payload)
    (dest / "search_one_result.html").write_text(found_html, encoding="utf-8")
    ca = extract_ca_token(found_html)
    if not ca:
        raise RuntimeError(
            f"[trf5] sample capture failed: no ca token for {FOUND_CNJ!r} — "
            "process may have been archived or sigilo-protected."
        )
    print(f"[trf5]   found ca token: {ca}")

    detail_html = fetch_detail(scraper.session, ca)
    (dest / "detail_normal.html").write_text(detail_html, encoding="latin-1")

    missing_payload = build_search_payload(
        format_cnj(clean_cnj(MISSING_CNJ)), field_ids
    )
    missing_html = submit_search(scraper.session, missing_payload)
    (dest / "search_no_results.html").write_text(missing_html, encoding="utf-8")
    print(f"[trf5] ALL samples written to {dest}")


if __name__ == "__main__":
    main()
