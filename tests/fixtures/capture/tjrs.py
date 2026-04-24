"""Capture cjsg samples for TJRS.

Run from repo root::

    python -m tests.fixtures.capture.tjrs

Post-processes each captured sample to drop bulk UI metadata
(``facet_counts``, ``highlighting``, ...) and truncates Base64 document
blobs (``documento_text`` / ``documento_text_aspas``). The parser only
reads ``response.docs``, so the trimmed payload preserves contract
coverage while keeping each sample under ~100 KB.
"""
import json
from urllib.parse import urlencode

import requests

from juscraper.courts.tjrs.download import BASE_URL, build_cjsg_inner_payload

from ._util import dump, samples_dir_for

# Top-level keys the parser ignores; safe to drop from saved samples.
_TOPLEVEL_DROP = {"facet_counts", "highlighting", "url", "query", "facets", "pages", "filtro", "hlq"}

# Per-doc fields: truncate heavy Base64 blobs; drop *_aspas duplicates.
_DOC_TRUNCATE = {
    "documento_text": 200,
    "documento_text_aspas": 0,
    "ementa_completa_aspas": 0,
    "ementa_referencia_aspas": 0,
}


def _truncate(val, max_len: int):
    if val is None or max_len == 0:
        return None
    if isinstance(val, list):
        return [_truncate(v, max_len) for v in val]
    if isinstance(val, str) and len(val) > max_len:
        return val[:max_len] + "..."
    return val


def _minify(raw: bytes) -> bytes:
    data = json.loads(raw)
    for key in _TOPLEVEL_DROP:
        data.pop(key, None)
    for doc in data.get("response", {}).get("docs", []) or []:
        for field, max_len in _DOC_TRUNCATE.items():
            if field not in doc:
                continue
            if max_len == 0:
                doc.pop(field)
            else:
                doc[field] = _truncate(doc[field], max_len)
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    payload = build_cjsg_inner_payload(pesquisa, pagina)
    data = {
        "action": "consultas_solr_ajax",
        "metodo": "buscar_resultados",
        "parametros": urlencode(payload, doseq=True),
    }
    response = session.post(BASE_URL, data=data, timeout=30)
    response.raise_for_status()
    dump(dest / filename, _minify(response.content))
    print(f"[tjrs] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJRS."""
    dest = samples_dir_for("tjrs", "cjsg")
    session = requests.Session()

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")


if __name__ == "__main__":
    main()
