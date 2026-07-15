"""Characterization tests for the TJSC result-item parser."""
from bs4 import BeautifulSoup

from juscraper.courts.tjsc.parse import _parse_result_item
from tests._helpers import load_sample


def _sample_items() -> dict[str, object]:
    soup = BeautifulSoup(
        load_sample("tjsc", "cjsg/result_item_variants.html"),
        "html.parser",
    )
    return {item["id"]: item for item in soup.find_all("div", class_="resultadoItem")}


def test_parse_result_item_preserves_process_class_and_summary_precedence():
    """An explicit EMENTA wins over a later DECISÃO label."""
    result = _parse_result_item(_sample_items()["direct-labels"])

    assert result == {
        "processo": "5001234-56.2024.8.24.0000",
        "classe": "Agravo de Instrumento",
        "orgao_julgador": "Primeira Câmara",
        "relator": "Desembargadora Ana",
        "ementa": "Ementa preferencial",
        "decisao": "Decisão posterior",
    }


def test_parse_result_item_preserves_normalized_labels_decision_fallback_and_unknown_ignore():
    """Unaccented variants map directly and DECISÃO supplies a missing ementa."""
    result = _parse_result_item(_sample_items()["normalized-labels"])

    assert result == {
        "orgao_julgador": "Segunda Câmara",
        "data_publicacao": "02/07/2025",
        "ementa": "Decisão usada como ementa",
    }


def test_parse_result_item_preserves_partial_matching():
    """Known labels embedded in longer text keep the first matching field."""
    result = _parse_result_item(_sample_items()["partial-labels"])

    assert result == {
        "relator": "Desembargador Bruno",
        "data_julgamento": "01/07/2025",
    }


def test_parse_result_item_preserves_zip_truncation():
    """A label without a corresponding value is ignored by pair truncation."""
    result = _parse_result_item(_sample_items()["truncated-pairs"])

    assert result == {"uf": "SC"}
