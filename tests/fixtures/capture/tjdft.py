"""Capture cjsg samples for TJDFT.

Run from repo root::

    python -m tests.fixtures.capture.tjdft
"""
import requests

from ._util import dump, samples_dir_for

BASE_URL = "https://jurisdf.tjdft.jus.br/api/v1/pesquisa"


def _payload(pesquisa: str, pagina: int, tamanho: int = 10) -> dict:
    return {
        "query": pesquisa,
        "termosAcessorios": [],
        "pagina": pagina,
        "tamanho": tamanho,
        "sinonimos": True,
        "espelho": True,
        "inteiroTeor": False,
        "retornaInteiroTeor": False,
        "retornaTotalizacao": True,
    }


def _capture(session: requests.Session, dest, pesquisa: str, pagina: int, filename: str) -> None:
    response = session.post(BASE_URL, json=_payload(pesquisa, pagina), timeout=30)
    response.raise_for_status()
    dump(dest / filename, response.content)
    print(f"[tjdft] wrote {filename}")


def main() -> None:
    """Capture cjsg JSON samples for TJDFT."""
    dest = samples_dir_for("tjdft", "cjsg")
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    _capture(session, dest, "dano moral", 1, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 2, "results_normal_page_02.json")
    _capture(session, dest, "mandado de seguranca", 1, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 1, "no_results.json")


if __name__ == "__main__":
    main()
