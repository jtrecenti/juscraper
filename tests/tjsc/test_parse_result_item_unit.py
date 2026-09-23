"""Unit tests for the TJSC result-item parser.

Most tests characterize behavior kept from the original parser. The tests on
the ``/TJSC`` suffix and on ``DECISÃO`` lock fixes: they fail against the
parser that predates them.
"""
from bs4 import BeautifulSoup

from juscraper.courts.tjsc.parse import _parse_result_item, cjsg_parse_manager
from tests._helpers import load_sample


def _sample_items() -> dict[str, object]:
    soup = BeautifulSoup(
        load_sample("tjsc", "cjsg/result_item_variants.html"),
        "html.parser",
    )
    return {item["id"]: item for item in soup.find_all("div", class_="resultadoItem")}


def test_parse_result_item_strips_tjsc_suffix_and_keeps_later_decision():
    """The ``/TJSC`` suffix is dropped and a later DECISÃO stays next to EMENTA."""
    result = _parse_result_item(_sample_items()["direct-labels"])

    assert result == {
        "processo": "5001234-56.2024.8.24.0000",
        "classe": "Agravo de Instrumento",
        "orgao_julgador": "Primeira Câmara",
        "relator": "Desembargadora Ana",
        "ementa": "Ementa preferencial",
        "decisao": "Decisão posterior",
    }


def test_parse_result_item_fills_ementa_from_decisao_and_keeps_both():
    """DECISÃO fills a missing ementa and stays as its own field.

    Unaccented label variants map directly and unknown labels are ignored.
    """
    result = _parse_result_item(_sample_items()["normalized-labels"])

    assert result == {
        "orgao_julgador": "Segunda Câmara",
        "data_publicacao": "02/07/2025",
        "ementa": "Decisão usada como ementa",
        "decisao": "Decisão usada como ementa",
    }


def test_parse_result_item_keeps_decision_when_it_precedes_explicit_summary():
    """DECISÃO remains available when a later EMENTA takes precedence."""
    result = _parse_result_item(_sample_items()["decision-before-summary"])

    assert result == {
        "decisao": "Decisão preservada",
        "ementa": "Ementa preferencial",
    }


def test_parse_result_item_preserves_partial_matching():
    """Known labels embedded in longer text keep the first matching field."""
    result = _parse_result_item(_sample_items()["partial-labels"])

    assert result == {
        "relator": "Desembargador Bruno",
        "data_julgamento": "01/07/2025",
    }


def test_parse_result_item_stops_class_search_at_first_hyphenated_line():
    """The first uppercase line with "-" but without " - " ends the class search.

    A later line in the "SIGLA - Classe" shape is not read, so no ``classe``.
    """
    result = _parse_result_item(_sample_items()["class-stops-at-first-hyphenated-line"])

    assert result == {"processo": "5009876-54.2024.8.24.0000"}


def test_parse_result_item_preserves_zip_truncation():
    """A label without a corresponding value is ignored by pair truncation."""
    result = _parse_result_item(_sample_items()["truncated-pairs"])

    assert result == {"uf": "SC"}


def test_cjsg_parse_manager_drops_items_without_ementa_or_processo():
    """Items with neither ``ementa`` nor ``processo`` do not become rows.

    ``partial-labels`` and ``truncated-pairs`` are dropped; the other four stay.
    """
    df = cjsg_parse_manager([load_sample("tjsc", "cjsg/result_item_variants.html")])

    assert len(_sample_items()) == 6
    assert len(df) == 4
    assert df[["processo", "ementa"]].notna().any(axis=1).all()
