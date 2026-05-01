"""Cobertura dos novos formatos extendidos de ``ano_ajuizamento`` e ``classe``.

- ``ano_ajuizamento``: ``int`` (retro-compat) | ``tuple[int, int]`` (range
  inclusivo) | ``list[int]`` (anos discretos).
- ``classe``: ``str`` (retro-compat) | ``list[str]`` (varios codigos OR-ed
  via ``terms`` no ES).

Os testes usam o ``build_*_payload`` direto pra validar a forma do payload
Elasticsearch — caminho minimo, sem mockar API.
"""

from __future__ import annotations

import pytest

from juscraper.aggregators.datajud.download import (
    build_contar_processos_payload,
    build_listar_processos_payload,
)


# ---------------------------------------------------------------------------
# ano_ajuizamento — 3 formas
# ---------------------------------------------------------------------------


def test_listar_int_gera_should_com_dois_ranges_iso_e_compacto():
    payload = build_listar_processos_payload(ano_ajuizamento=2023)
    must = payload["query"]["bool"]["must"]
    ano_clause = next(c for c in must if "bool" in c)
    shoulds = ano_clause["bool"]["should"]
    assert len(shoulds) == 2
    formats = {next(iter(s["range"]["dataAjuizamento"].values())) for s in shoulds}
    # Um deve estar em formato ISO, outro em formato compacto
    assert "2023-01-01" in formats
    assert "20230101000000" in formats


def test_contar_int_gera_should_com_dois_ranges():
    payload = build_contar_processos_payload(ano_ajuizamento=2023)
    must = payload["query"]["bool"]["must"]
    ano_clause = next(c for c in must if "bool" in c)
    assert len(ano_clause["bool"]["should"]) == 2


# ---------------------------------------------------------------------------
# ano_ajuizamento — tuple (range inclusivo)
# ---------------------------------------------------------------------------


def test_tuple_range_2020_2024_gera_5_anos_x_2_formatos():
    """``(2020, 2024)`` deve cobrir 5 anos × 2 formatos = 10 ranges no should."""
    payload = build_contar_processos_payload(ano_ajuizamento=(2020, 2024))
    must = payload["query"]["bool"]["must"]
    ano_clause = next(c for c in must if "bool" in c)
    shoulds = ano_clause["bool"]["should"]
    assert len(shoulds) == 10  # 5 anos × 2 formatos

    anos_iso = sorted({
        s["range"]["dataAjuizamento"]["gte"][:4]
        for s in shoulds
        if "-" in s["range"]["dataAjuizamento"]["gte"]
    })
    assert anos_iso == ["2020", "2021", "2022", "2023", "2024"]


def test_tuple_invertida_e_normalizada():
    """``(2024, 2020)`` é equivalente a ``(2020, 2024)`` — ordem não importa."""
    a = build_contar_processos_payload(ano_ajuizamento=(2020, 2024))
    b = build_contar_processos_payload(ano_ajuizamento=(2024, 2020))
    assert a == b


def test_tuple_mesmo_ano_e_equivalente_a_int():
    """``(2023, 2023)`` deve dar o mesmo payload que ``2023``."""
    a = build_contar_processos_payload(ano_ajuizamento=2023)
    b = build_contar_processos_payload(ano_ajuizamento=(2023, 2023))
    assert a == b


def test_tuple_com_3_elementos_levanta():
    with pytest.raises(ValueError, match="2 elementos"):
        build_contar_processos_payload(ano_ajuizamento=(2020, 2022, 2024))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# ano_ajuizamento — list (anos discretos)
# ---------------------------------------------------------------------------


def test_list_de_3_anos_gera_3_x_2_ranges():
    payload = build_contar_processos_payload(ano_ajuizamento=[2020, 2022, 2024])
    must = payload["query"]["bool"]["must"]
    ano_clause = next(c for c in must if "bool" in c)
    assert len(ano_clause["bool"]["should"]) == 6  # 3 anos × 2 formatos
    anos_iso = sorted({
        s["range"]["dataAjuizamento"]["gte"][:4]
        for s in ano_clause["bool"]["should"]
        if "-" in s["range"]["dataAjuizamento"]["gte"]
    })
    assert anos_iso == ["2020", "2022", "2024"]


def test_list_vazia_nao_gera_clausula():
    """``ano_ajuizamento=[]`` deve ser equivalente a ``None`` — sem clausula."""
    a = build_contar_processos_payload()
    b = build_contar_processos_payload(ano_ajuizamento=[])
    assert a == b


def test_list_com_1_ano_e_equivalente_a_int():
    a = build_contar_processos_payload(ano_ajuizamento=2023)
    b = build_contar_processos_payload(ano_ajuizamento=[2023])
    assert a == b


# ---------------------------------------------------------------------------
# classe — str (retro-compat) | list[str]
# ---------------------------------------------------------------------------


def test_classe_str_unica_gera_match():
    payload = build_contar_processos_payload(classe="436")
    must = payload["query"]["bool"]["must"]
    assert {"match": {"classe.codigo": "436"}} in must


def test_classe_lista_com_um_elemento_gera_match():
    """Lista com 1 elemento → ``match`` (igual ao caso str)."""
    payload = build_contar_processos_payload(classe=["436"])
    must = payload["query"]["bool"]["must"]
    assert {"match": {"classe.codigo": "436"}} in must


def test_classe_lista_com_n_elementos_gera_terms():
    payload = build_contar_processos_payload(classe=["436", "159", "22"])
    must = payload["query"]["bool"]["must"]
    assert {"terms": {"classe.codigo": ["436", "159", "22"]}} in must


def test_classe_lista_filtra_vazias_e_strip():
    """Strings vazias são descartadas; brancos não fazem terms estourar."""
    payload = build_contar_processos_payload(classe=["", "436", "  ", "159"])
    must = payload["query"]["bool"]["must"]
    assert {"terms": {"classe.codigo": ["436", "159"]}} in must


def test_classe_lista_vazia_nao_gera_clausula():
    a = build_contar_processos_payload()
    b = build_contar_processos_payload(classe=[])
    assert a == b


def test_classe_mesma_no_listar_processos():
    """``classe`` na ``listar_processos`` segue o mesmo contrato."""
    payload = build_listar_processos_payload(classe=["7", "159"])
    must = payload["query"]["bool"]["must"]
    assert {"terms": {"classe.codigo": ["7", "159"]}} in must


# ---------------------------------------------------------------------------
# Combinação: range + lista de classes (caso real do labdados)
# ---------------------------------------------------------------------------


def test_caso_real_viabilidade_labdados():
    """Caso típico do escritório de apoio do LabDados:

    - 5 anos (2020 a 2024)
    - 2 classes (Procedimento Comum + Apelação Cível)
    - 1 assunto (Saúde Suplementar)
    """
    payload = build_contar_processos_payload(
        ano_ajuizamento=(2020, 2024),
        classe=["7", "436"],
        assuntos=["7780"],
    )

    assert payload["size"] == 0
    assert payload["track_total_hits"] is True

    must = payload["query"]["bool"]["must"]
    # Tem clausula de ano (10 should)
    ano_clause = next(c for c in must if "bool" in c)
    assert len(ano_clause["bool"]["should"]) == 10
    # Tem clausula de classe (terms)
    assert {"terms": {"classe.codigo": ["7", "436"]}} in must
    # Tem clausula de assunto
    assert {"terms": {"assuntos.codigo": ["7780"]}} in must
