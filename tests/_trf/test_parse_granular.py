"""Testes granulares do parser de detalhe da família ``_trf``.

O ramo ``ID: <id> - <data> - <descrição>`` dos documentos só aparece nos
samples de ``tests/_trf/samples/cpopg/`` (PJe JSF capturado antes da troca
do TRF3 para a API). As páginas do TRF1 e do TRF5 listam os documentos sem o
prefixo ``ID:`` e caem no ramo que guarda só a descrição.
"""
from __future__ import annotations

from juscraper.courts._trf.parse import parse_detail
from tests._helpers import load_sample_bytes


def _detail(tribunal: str, nome: str) -> str:
    return load_sample_bytes(tribunal, f"cpopg/{nome}").decode("latin-1")


def test_documentos_com_prefixo_id_separam_id_data_e_descricao() -> None:
    """Linha ``ID: 578698643 - 2026-04-29 ... - Despacho`` preenche ``id`` e ``data``."""
    documentos = parse_detail(_detail("_trf", "detail_normal.html"))["documentos"]

    assert documentos
    primeiro = documentos[0]
    assert primeiro["id"] == "578698643"
    assert primeiro["data"] is not None and primeiro["data"].startswith("2026")
    assert "Despacho (Despacho)" in primeiro["descricao"]
    assert all(doc["id"] and doc["id"].isdigit() for doc in documentos)


def test_documentos_sem_prefixo_id_guardam_so_a_descricao() -> None:
    """No layout do TRF1, sem ``ID:``, ``id`` e ``data`` ficam ``None`` e a linha inteira vai para ``descricao``."""
    documentos = parse_detail(_detail("trf1", "detail_normal.html"))["documentos"]

    assert documentos
    assert documentos[0] == {
        "id": None,
        "data": None,
        "descricao": "09/10/2025 19:34:46 - Despacho (Despacho)",
    }
