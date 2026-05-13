"""Coercao dos tipos IdFiltro / IdFiltroUnico (refs #232).

Cobre a forma como os Annotated+BeforeValidator do schema convertem entradas
``int``/``str``/``list`` em ``str | None`` (CSV) — ou rejeitam, no caso de
``IdFiltroUnico`` recebendo lista.

Os testes usam :class:`InputCJSGTJSP` e :class:`InputCJPGTJSP` como instancias
do tipo (em vez de validar o ``IdFiltro`` isolado), porque pydantic so resolve
o ``BeforeValidator`` dentro de um ``BaseModel``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from juscraper.courts.tjsp.schemas import InputCJPGTJSP, InputCJSGTJSP


class TestIdFiltroCoercion:
    """``IdFiltro`` aceita int/str/list e coage para ``str | None`` (CSV)."""

    def test_int_vira_string(self):
        m = InputCJSGTJSP(pesquisa="x", classe=417)
        assert m.classe == "417"

    def test_str_passa_inalterado(self):
        m = InputCJSGTJSP(pesquisa="x", classe="417")
        assert m.classe == "417"

    def test_lista_de_int_vira_csv(self):
        m = InputCJSGTJSP(pesquisa="x", assunto=[3607, 5885, 6317])
        assert m.assunto == "3607,5885,6317"

    def test_lista_de_str_vira_csv(self):
        m = InputCJSGTJSP(pesquisa="x", assunto=["3607", "5885"])
        assert m.assunto == "3607,5885"

    def test_lista_mista_int_str(self):
        m = InputCJSGTJSP(pesquisa="x", assunto=[3607, "5885", 6317])
        assert m.assunto == "3607,5885,6317"

    def test_csv_string_passa_inalterado(self):
        """Backend ja interpreta CSV; passar string CSV direto deve ser idempotente."""
        m = InputCJSGTJSP(pesquisa="x", assunto="3607,5885,6317")
        assert m.assunto == "3607,5885,6317"

    def test_none_continua_none(self):
        m = InputCJSGTJSP(pesquisa="x", classe=None)
        assert m.classe is None

    def test_default_e_none(self):
        m = InputCJSGTJSP(pesquisa="x")
        assert m.classe is None
        assert m.assunto is None
        assert m.orgao_julgador is None

    def test_lista_vazia_vira_none(self):
        """Lista vazia equivale a 'sem filtro' (==None), nao a CSV vazio."""
        m = InputCJSGTJSP(pesquisa="x", classe=[])
        assert m.classe is None


class TestIdFiltroUnicoRejeita:
    """``IdFiltroUnico`` (usado em ``comarca``) rejeita ``list``."""

    def test_comarca_int(self):
        m = InputCJSGTJSP(pesquisa="x", comarca=1)
        assert m.comarca == "1"

    def test_comarca_str(self):
        m = InputCJSGTJSP(pesquisa="x", comarca="100")
        assert m.comarca == "100"

    def test_comarca_lista_rejeita(self):
        with pytest.raises(ValidationError):
            InputCJSGTJSP(pesquisa="x", comarca=[1, 2])


class TestCJPGAceitaSingularComIdFiltro:
    """``cjpg`` (TJSP) agora aceita ``classe``/``assunto``/``vara`` singulares."""

    def test_classe_int(self):
        m = InputCJPGTJSP(classe=12728)
        assert m.classe == "12728"

    def test_assunto_lista(self):
        m = InputCJPGTJSP(assunto=[3607, 5885])
        assert m.assunto == "3607,5885"

    def test_vara_string_no_formato_arvore(self):
        m = InputCJPGTJSP(vara="1-1-1")
        assert m.vara == "1-1-1"

    def test_vara_lista_string(self):
        m = InputCJPGTJSP(vara=["1-1-1", "2-2-2"])
        assert m.vara == "1-1-1,2-2-2"
