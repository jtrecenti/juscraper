"""Regras do schema ``InputCJSGTJRO`` que valem so para o TJRO.

As tabelas que cruzam tribunais ficam em ``tests/schemas/test_domain_rejection.py``.
"""
from __future__ import annotations

from juscraper.courts.tjro.schemas import InputCJSGTJRO


class TestTJROOrgaoJulgadorIntZero:
    """TJRO ``orgao_julgador`` aceita ``int | str | None`` e preserva o ``0`` (int).

    O ``0`` não pode ser confundido com ``None`` nem com ``""``. Protege o
    ternário ``inp.orgao_julgador if inp.orgao_julgador is not None else ""``
    no client (o ingênuo ``or ""`` quebraria o caso).
    """

    def test_orgao_julgador_zero_int_preserved(self):
        inp = InputCJSGTJRO(pesquisa="x", orgao_julgador=0)
        assert inp.orgao_julgador == 0
        assert inp.orgao_julgador is not None

    def test_orgao_julgador_colegiado_zero_int_preserved(self):
        inp = InputCJSGTJRO(pesquisa="x", orgao_julgador_colegiado=0)
        assert inp.orgao_julgador_colegiado == 0
        assert inp.orgao_julgador_colegiado is not None
