"""Regras do schema ``InputCJSGTJRN`` que valem so para o TJRN.

As tabelas que cruzam tribunais ficam em ``tests/schemas/test_domain_rejection.py``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from juscraper.courts.tjrn.schemas import InputCJSGTJRN


@pytest.mark.parametrize("jurisdicoes", ["TJ", "TR"])
def test_tjrn_recusa_jurisdicao_com_primeiro_grau(jurisdicoes):
    """``"TJ"`` e ``"TR"`` so cobrem o 2o grau; com ``grau="1"`` o portal da 0 resultados."""
    with pytest.raises(ValidationError, match="2o grau"):
        InputCJSGTJRN(pesquisa="x", jurisdicoes=jurisdicoes, grau="1")


@pytest.mark.parametrize(
    "filtros",
    [
        {"jurisdicoes": "TJ", "grau": "2"},
        {"jurisdicoes": "TR", "grau": ""},
        {"jurisdicoes": "TJ", "grau": None},
        {"jurisdicoes": "", "grau": "1"},
        {"jurisdicoes": None, "grau": "1"},
    ],
)
def test_tjrn_aceita_jurisdicao_sem_primeiro_grau(filtros):
    # Sem termo, porque decisoes de 1o grau nao tem ementa, onde ``pesquisa`` busca.
    InputCJSGTJRN(pesquisa="", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença", "grau": "2"},
        {"decisoes": "Sentença", "jurisdicoes": "TJ"},
        {"decisoes": "Sentença", "jurisdicoes": "TR", "grau": ""},
        {"decisoes": "Sentença", "jurisdicoes": "TJ", "grau": "1"},
        {"decisoes": "Acórdão", "grau": "1"},
    ],
)
def test_tjrn_recusa_decisao_fora_do_seu_grau(filtros):
    """``"Sentença"`` so existe no 1o grau e ``"Acórdão"`` so no 2o; cruzadas, o portal da 0 resultados."""
    with pytest.raises(ValidationError, match="graus diferentes"):
        InputCJSGTJRN(pesquisa="x", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença", "grau": "1"},
        {"decisoes": "Sentença", "jurisdicoes": None, "grau": None},
        {"decisoes": "Acórdão", "grau": "2"},
        {"decisoes": "Acórdão", "jurisdicoes": "TJ"},
        {"decisoes": "Acórdão", "jurisdicoes": "TR"},
        {"decisoes": "Decisão", "grau": "1"},
        {"decisoes": "Decisão", "grau": "2"},
        {"decisoes": "Decisão", "jurisdicoes": "TJ"},
        {"decisoes": "Decisão", "jurisdicoes": "TR"},
    ],
)
def test_tjrn_aceita_decisao_no_seu_grau(filtros):
    # Sem termo, porque sentencas e monocraticas nao tem ementa, onde ``pesquisa`` busca.
    InputCJSGTJRN(pesquisa="", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença"},
        {"grau": "1"},
        {"decisoes": "Decisão", "grau": "1"},
        {"decisoes": "Decisão", "jurisdicoes": "TJ"},
        {"decisoes": "Decisão", "jurisdicoes": "TR", "grau": "2"},
        {"decisoes": "Decisão", "sistema": "PJE"},
    ],
)
def test_tjrn_recusa_termo_na_ementa_sem_ementa(filtros):
    """So os acordaos tem ementa: com termo na ementa, os demais dao 0 resultados no portal.

    Sentencas, decisoes de 1o grau e monocraticas de ``"TJ"``, ``"TR"`` ou do
    PJe nao tem ementa.
    """
    with pytest.raises(ValidationError, match="so os acordaos tem ementa"):
        InputCJSGTJRN(pesquisa="dano moral", **filtros)


@pytest.mark.parametrize("pesquisa", ["x", "A", "a dano", "de,", '"dano moral"'])
def test_tjrn_recusa_termo_com_palavra_que_o_portal_nao_ignora(pesquisa):
    """O portal so ignora preposicoes e "e"/"ou" em minusculas e sem pontuacao."""
    with pytest.raises(ValidationError, match="so os acordaos tem ementa"):
        InputCJSGTJRN(pesquisa=pesquisa, grau="1")


@pytest.mark.parametrize(
    ("pesquisa", "filtros"),
    [
        # Sem termo, ou so com palavras que o portal ignora: a busca traz tudo do filtro.
        ("", {"decisoes": "Sentença"}),
        ("   ", {"grau": "1"}),
        ("a", {"decisoes": "Sentença"}),
        ("de", {"grau": "1"}),
        ("a de para", {"decisoes": "Decisão", "jurisdicoes": "TJ"}),
        ('"a"', {"decisoes": "Decisão", "sistema": "PJE"}),
        # No inteiro teor, que sentencas e monocraticas tem.
        ("dano moral", {"decisoes": "Sentença", "buscar_em": "inteiro_teor"}),
        ("dano moral", {"grau": "1", "buscar_em": "inteiro_teor"}),
        ("dano moral", {"decisoes": "Decisão", "jurisdicoes": "TR", "buscar_em": "inteiro_teor"}),
        # Acordaos tem ementa; ha monocraticas antigas do SAJ com ementa, sem jurisdicao.
        ("dano moral", {"decisoes": "Acórdão"}),
        ("dano moral", {"decisoes": "Acórdão", "jurisdicoes": "TJ", "grau": "2"}),
        ("dano moral", {"grau": "2"}),
        ("dano moral", {"jurisdicoes": "TR"}),
        ("apelação", {"decisoes": "Decisão"}),
        ("apelação", {"decisoes": "Decisão", "grau": "2"}),
        ("apelação", {"decisoes": "Decisão", "sistema": "SAJ"}),
        ("dano moral", {"decisoes": "Acórdão", "sistema": "PJE"}),
    ],
)
def test_tjrn_aceita_termo_na_ementa_de_quem_tem(pesquisa, filtros):
    InputCJSGTJRN(pesquisa=pesquisa, **filtros)
