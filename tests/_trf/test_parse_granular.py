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


def test_documentos_com_prefixo_id_separam_o_id_e_cortam_a_data_no_primeiro_hifen() -> None:
    """Linha ``ID: 578698643 - 2026-04-29 12:37:07.255 - Despacho (Despacho)``.

    O ``id`` sai certo. A data não: o separador entre os campos é ``-``, o
    mesmo caractere da data ISO, então ``data`` fica só com o ano e o resto da
    data vai para o início de ``descricao``. É limitação conhecida da
    expressão de ``_trf/parse.py`` para esse ramo, que o TRF1 e o TRF5 não
    exercitam hoje. O teste fixa a saída atual para que a correção da
    expressão apareça como mudança deliberada deste teste.
    """
    documentos = parse_detail(_detail("_trf", "detail_normal.html"))["documentos"]

    assert documentos[0] == {
        "id": "578698643",
        "data": "2026",
        "descricao": "04-29 12:37:07.255 - Despacho (Despacho)",
    }
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
