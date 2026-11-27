"""Capture cjsg samples for TJBA.

Run from repo root::

    python -m tests.fixtures.capture.tjba
"""
import logging

import requests

from juscraper.courts.tjba.download import FILTER_QUERY

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudenciaws.tjba.jus.br/graphql"


def _payload(pesquisa: str, page_number: int, items_per_page: int = 10) -> dict:
    return {
        "operationName": "filter",
        "variables": {
            "decisaoFilter": {
                "assunto": pesquisa,
                "orgaos": [],
                "relatores": [],
                "classes": [],
                "dataInicial": "1980-02-01T03:00:00.000Z",
                "segundoGrau": True,
                "turmasRecursais": True,
                "tipoAcordaos": True,
                "tipoDecisoesMonocraticas": True,
                "ordenadoPor": "dataPublicacao",
            },
            "pageNumber": page_number,
            "itemsPerPage": items_per_page,
        },
        "query": FILTER_QUERY,
    }


def _capture(session: requests.Session, dest, pesquisa: str, page_number: int, filename: str) -> None:
    response = session.post(BASE_URL, json=_payload(pesquisa, page_number), timeout=60)
    response.raise_for_status()
    dump(dest / filename, response.content)
    logger.info("[tjba] wrote %s", filename)


def main() -> None:
    """Capture cjsg GraphQL samples for TJBA."""
    dest = samples_dir_for("tjba", "cjsg")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
        "Content-Type": "application/json",
    })

    _capture(session, dest, "dano moral", 0, "results_normal_page_01.json")
    _capture(session, dest, "dano moral", 1, "results_normal_page_02.json")
    _capture(session, dest, "consumidor", 0, "single_page.json")
    _capture(session, dest, "juscraper_probe_zero_hits_xyzqwe", 0, "no_results.json")
    # pageNumber 900 de uma busca com 65 páginas: além do total, dentro do teto de 10.000.
    _capture(session, dest, "enfiteuse laudêmio", 900, "alem_do_total.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
