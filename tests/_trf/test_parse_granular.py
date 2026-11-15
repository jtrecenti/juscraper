"""Testes granulares do parser de detalhe da família ``_trf``.

O ramo ``ID: <id> - <data> - <descrição>`` dos documentos só aparece nos
samples de ``tests/_trf/samples/cpopg/`` (PJe JSF capturado antes da troca
do TRF3 para a API). As páginas do TRF1 e do TRF5 listam os documentos sem o
prefixo ``ID:`` e caem no ramo que guarda só a descrição.
"""
from __future__ import annotations

import re

from juscraper.courts._trf.parse import parse_detail
from tests._helpers import load_sample_bytes


def _detail(tribunal: str, nome: str) -> str:
    return load_sample_bytes(tribunal, f"cpopg/{nome}").decode("latin-1")


def test_documentos_com_prefixo_id_separam_id_data_e_descricao() -> None:
    """Linha ``ID: 578698643 - 2026-04-29 12:37:07.255 - Despacho (Despacho)``.

    O separador entre os campos é ``-``, o mesmo caractere da data ISO; a data
    sai inteira, com a hora, e só a descrição fica em ``descricao``.
    """
    documentos = parse_detail(_detail("_trf", "detail_normal.html"))["documentos"]

    assert documentos[0] == {
        "id": "578698643",
        "data": "2026-04-29 12:37:07.255",
        "descricao": "Despacho (Despacho)",
    }
    assert all(doc["id"] and doc["id"].isdigit() for doc in documentos)


def test_documentos_com_prefixo_id_e_milissegundos_curtos() -> None:
    """Na página paginada o PJe corta zeros dos milissegundos (``13:44:34.33``)."""
    documentos = parse_detail(_detail("_trf", "detail_paginated.html"))["documentos"]

    assert documentos
    assert all(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", doc["data"] or "") for doc in documentos)
    assert not any(re.match(r"\d", doc["descricao"] or "") for doc in documentos)


def test_documentos_sem_prefixo_id_guardam_so_a_descricao() -> None:
    """No layout do TRF1, sem ``ID:``, ``id`` e ``data`` ficam ``None`` e a linha inteira vai para ``descricao``."""
    documentos = parse_detail(_detail("trf1", "detail_normal.html"))["documentos"]

    assert documentos
    assert documentos[0] == {
        "id": None,
        "data": None,
        "descricao": "09/10/2025 19:34:46 - Despacho (Despacho)",
    }
