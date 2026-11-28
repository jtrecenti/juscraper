"""Regras do schema ``InputCJSGTJRJ`` que valem so para o TJRJ.

As tabelas que cruzam tribunais ficam em ``tests/schemas/test_domain_rejection.py``.
"""
from __future__ import annotations

from typing import get_args

from juscraper.courts.tjrj.download import extract_select_options
from juscraper.courts.tjrj.schemas import InputCJSGTJRJ
from tests._helpers import load_sample


def test_tjrj_competencia_e_origem_batem_com_os_seletores_do_ejuris():
    """Origens do form inicial; competências da origem padrão e da Turma Recursal (#207)."""
    def opcoes(html: str, campo: str) -> set[str]:
        valores = extract_select_options(html, campo)
        assert valores, campo
        return set(valores)

    inicial = load_sample("tjrj", "cjsg/post_initial.html")
    turma_recursal = load_sample("tjrj", "cjsg/postback_origem_turma_recursal.html")
    campos = InputCJSGTJRJ.model_fields
    assert set(get_args(campos["origem"].annotation)) == opcoes(inicial, "cmbOrigem")
    # ``competencia`` e ``Literal[...] | None``: ``None`` usa o padrao do form.
    literal_competencia, nenhum = get_args(campos["competencia"].annotation)
    assert nenhum is type(None)
    assert set(get_args(literal_competencia)) == (
        opcoes(inicial, "cmbCompetencia") | opcoes(turma_recursal, "cmbCompetencia")
    )
