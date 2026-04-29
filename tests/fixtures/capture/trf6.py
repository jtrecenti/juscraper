"""Capture cpopg samples for TRF6 against the live eproc deployment.

Run from repo root::

    python -m tests.fixtures.capture.trf6

Writes ``form_initial.html``, ``detail_normal.html``,
``search_no_results.html`` and ``search_bad_captcha.html`` to
``tests/trf6/samples/cpopg/``.

Goes through the *real* scraper helpers in
:mod:`juscraper.courts.trf6.download` — using the same payload-builder and
captcha-extraction code as the production code path, so any drift between
the scraper and what the live tribunal actually accepts breaks this script
first (instead of silently producing stale samples).

Captcha-protected: this script needs the optional :mod:`txtcaptcha`
dependency installed (``uv pip install txtcaptcha``). Each captcha solve
downloads a HuggingFace pretrained CRNN on first call (cached afterwards).
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

import juscraper as jus
from juscraper.courts.trf6.download import (
    BROWSER_HEADERS,
    build_search_payload,
    extract_captcha_b64,
    fetch_form,
    is_captcha_error,
    is_detail_page,
    solve_captcha,
    submit_search,
)
from juscraper.utils.cnj import clean_cnj, format_cnj

REPO_ROOT = Path(__file__).resolve().parents[3]

# JEF process at 3ª Vara Cível e JEF de Juiz de Fora (MG), pulled from
# data/amostra_jf_primeiro_grau.csv. Recent and likely to keep matching.
FOUND_CNJ = "10052295520234063801"
# Synthetic CNJ shaped like a TRF6 process so the form mask validation passes;
# eproc re-serves the form with no error when nothing matches.
MISSING_CNJ = "00000000020994060000"


def _fresh_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(BROWSER_HEADERS)
    return s


def _capture_detail(dest: Path, max_attempts: int = 5) -> None:
    """Loop until txtcaptcha solves a captcha that the backend accepts."""
    for attempt in range(1, max_attempts + 1):
        s = _fresh_session()
        form_html = fetch_form(s)
        if attempt == 1:
            (dest / "form_initial.html").write_text(form_html, encoding="latin-1")
            print(f"[trf6]   saved form_initial.html ({len(form_html)} chars)")
        captcha_b64 = extract_captcha_b64(form_html)
        captcha_text = solve_captcha(captcha_b64)
        payload = build_search_payload(format_cnj(clean_cnj(FOUND_CNJ)), captcha_text)
        response = submit_search(s, payload)
        if is_detail_page(response):
            (dest / "detail_normal.html").write_text(response, encoding="latin-1")
            print(
                f"[trf6]   saved detail_normal.html "
                f"(attempt {attempt}, captcha={captcha_text!r})"
            )
            return
        if is_captcha_error(response):
            print(f"[trf6]   attempt {attempt}: captcha {captcha_text!r} rejected")
            time.sleep(1)
            continue
        raise RuntimeError(
            f"[trf6] CNJ {FOUND_CNJ!r} did not produce a detail page — "
            "process may have been archived or sigilo-protected."
        )
    raise RuntimeError(
        f"[trf6] captcha solver failed {max_attempts} attempts on FOUND_CNJ"
    )


def _capture_no_results(dest: Path, max_attempts: int = 5) -> None:
    """Capture the response when the CNJ doesn't match anything."""
    for attempt in range(1, max_attempts + 1):
        s = _fresh_session()
        form_html = fetch_form(s)
        captcha_b64 = extract_captcha_b64(form_html)
        captcha_text = solve_captcha(captcha_b64)
        payload = build_search_payload(format_cnj(clean_cnj(MISSING_CNJ)), captcha_text)
        response = submit_search(s, payload)
        if is_detail_page(response):
            raise RuntimeError(
                f"[trf6] MISSING_CNJ unexpectedly matched a process — "
                "pick a different synthetic value."
            )
        if is_captcha_error(response):
            print(f"[trf6]   attempt {attempt}: captcha {captcha_text!r} rejected")
            time.sleep(1)
            continue
        (dest / "search_no_results.html").write_text(response, encoding="latin-1")
        print(f"[trf6]   saved search_no_results.html (attempt {attempt})")
        return
    raise RuntimeError(
        f"[trf6] captcha solver failed {max_attempts} attempts on MISSING_CNJ"
    )


def _capture_bad_captcha(dest: Path) -> None:
    """Force a captcha rejection by submitting an obviously wrong value."""
    s = _fresh_session()
    fetch_form(s)  # primes the session
    payload = build_search_payload(format_cnj(clean_cnj(FOUND_CNJ)), "WRONG")
    response = submit_search(s, payload)
    (dest / "search_bad_captcha.html").write_text(response, encoding="latin-1")
    print("[trf6]   saved search_bad_captcha.html")


def main() -> None:
    """Capture cpopg samples for TRF6."""
    # Validate that the txtcaptcha optional dep is installed *before* hitting
    # the live tribunal — a fresher error message than a deep ImportError.
    try:
        import txtcaptcha  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "tests/fixtures/capture/trf6.py needs `txtcaptcha` installed "
            "(`uv pip install txtcaptcha`)."
        ) from exc

    dest = REPO_ROOT / "tests" / "trf6" / "samples" / "cpopg"
    dest.mkdir(parents=True, exist_ok=True)

    # Validate the scraper factory is wired correctly.
    jus.scraper("trf6")

    _capture_detail(dest)
    time.sleep(2)
    _capture_no_results(dest)
    time.sleep(2)
    _capture_bad_captcha(dest)
    print(f"[trf6] ALL samples written to {dest}")


if __name__ == "__main__":
    main()
