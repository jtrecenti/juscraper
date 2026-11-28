"""Regras dos schemas ``InputCJSGTJES``/``InputCJPGTJES`` que valem so para o TJES.

As tabelas que cruzam tribunais ficam em ``tests/schemas/test_domain_rejection.py``.
"""
from __future__ import annotations

from typing import get_args

import pytest
from pydantic import ValidationError

from juscraper.courts.tjes.schemas import ORDENACOES_POR_CORE, InputCJSGTJES, OrdenacaoCJPG, OrdenacaoCJSG


@pytest.mark.parametrize("core", sorted(ORDENACOES_POR_CORE.keys() - {"pje1g"}))
def test_tjes_cjsg_ordenacao_aceita_so_as_opcoes_do_core(core):
    aceitas = set(ORDENACOES_POR_CORE[core])
    todas = set(get_args(OrdenacaoCJSG))
    for valor in aceitas:
        InputCJSGTJES(pesquisa="x", core=core, ordenacao=valor)
    for valor in todas - aceitas:
        with pytest.raises(ValidationError, match="nao existe no core"):
            InputCJSGTJES(pesquisa="x", core=core, ordenacao=valor)
    assert InputCJSGTJES(pesquisa="x", core=core).ordenacao is None


def test_tjes_cjsg_ordenacao_cobre_as_opcoes_de_todos_os_cores():
    opcoes = {v for valores in ORDENACOES_POR_CORE.values() for v in valores}
    assert opcoes == set(get_args(OrdenacaoCJSG))
    assert set(ORDENACOES_POR_CORE["pje1g"]) == set(get_args(OrdenacaoCJPG))
