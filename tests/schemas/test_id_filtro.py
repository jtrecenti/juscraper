"""Coercao dos tipos IdFiltro / IdFiltroUnico (refs #232).

Cobre a forma como os Annotated+BeforeValidator convertem entradas
``int``/``str``/``list`` em ``str | None`` (CSV) — ou rejeitam, no caso de
``IdFiltroUnico`` recebendo lista.

Os tipos sao validados isolados por :class:`pydantic.TypeAdapter`, que aplica
o ``BeforeValidator`` como um campo de ``BaseModel`` aplicaria. A ligacao dos
tipos aos campos dos schemas fica em :class:`TestWiringNosSchemas`.
"""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from juscraper.courts._esaj.schemas import InputCJPGEsaj
from juscraper.courts.tjsp.schemas import InputCJSGTJSP
from juscraper.schemas import IdFiltro, IdFiltroUnico

ID_FILTRO: TypeAdapter[str | None] = TypeAdapter(IdFiltro)
ID_FILTRO_UNICO: TypeAdapter[str | None] = TypeAdapter(IdFiltroUnico)


class TestIdFiltroCoercion:
    """``IdFiltro`` aceita int/str/list e coage para ``str | None`` (CSV)."""

    def test_int_vira_string(self):
        assert ID_FILTRO.validate_python(417) == "417"

    def test_str_passa_inalterado(self):
        assert ID_FILTRO.validate_python("417") == "417"

    def test_lista_de_int_vira_csv(self):
        assert ID_FILTRO.validate_python([3607, 5885, 6317]) == "3607,5885,6317"

    def test_lista_de_str_vira_csv(self):
        assert ID_FILTRO.validate_python(["3607", "5885"]) == "3607,5885"

    def test_lista_mista_int_str(self):
        assert ID_FILTRO.validate_python([3607, "5885", 6317]) == "3607,5885,6317"

    def test_csv_string_passa_inalterado(self):
        """Backend ja interpreta CSV; passar string CSV direto deve ser idempotente."""
        assert ID_FILTRO.validate_python("3607,5885,6317") == "3607,5885,6317"

    def test_none_continua_none(self):
        assert ID_FILTRO.validate_python(None) is None

    def test_lista_vazia_vira_none(self):
        """Lista vazia equivale a 'sem filtro' (==None), nao a CSV vazio."""
        assert ID_FILTRO.validate_python([]) is None


class TestIdFiltroUnicoRejeita:
    """``IdFiltroUnico`` (usado em ``comarca``) rejeita ``list``."""

    def test_int(self):
        assert ID_FILTRO_UNICO.validate_python(1) == "1"

    def test_str(self):
        assert ID_FILTRO_UNICO.validate_python("100") == "100"

    def test_lista_rejeita(self):
        with pytest.raises(ValidationError):
            ID_FILTRO_UNICO.validate_python([1, 2])


class TestWiringNosSchemas:
    """Os campos de filtro do ``cjsg`` e do ``cjpg`` (TJSP) usam os tipos acima."""

    def test_cjsg_default_e_none(self):
        m = InputCJSGTJSP(pesquisa="x")
        assert m.classe is None
        assert m.assunto is None
        assert m.orgao_julgador is None

    def test_cjsg_filtros_aceitam_int_e_lista(self):
        m = InputCJSGTJSP(pesquisa="x", classe=417, assunto=[1, "2"], orgao_julgador="0-5")
        assert (m.classe, m.assunto, m.orgao_julgador) == ("417", "1,2", "0-5")

    def test_cjsg_comarca_lista_rejeita(self):
        with pytest.raises(ValidationError):
            InputCJSGTJSP(pesquisa="x", comarca=[1, 2])

    def test_cjpg_classe_int(self):
        m = InputCJPGEsaj(classe=12728)
        assert m.classe == "12728"

    def test_cjpg_assunto_lista(self):
        m = InputCJPGEsaj(assunto=[3607, 5885])
        assert m.assunto == "3607,5885"

    def test_cjpg_vara_string_no_formato_arvore(self):
        m = InputCJPGEsaj(vara="1-1-1")
        assert m.vara == "1-1-1"

    def test_cjpg_vara_lista_string(self):
        m = InputCJPGEsaj(vara=["1-1-1", "2-2-2"])
        assert m.vara == "1-1-1,2-2-2"


class TestJsonSchemaIdFiltro:
    """O JSON schema de entrada lista as formas aceitas; o de saída, ``str | None``.

    ``IdFiltro`` é anotado com o tipo de saída e guarda o de entrada em
    ``json_schema_input_type``; sem ele, o schema de entrada anunciaria só
    ``string``/``null`` e esconderia ``int`` e ``list``.
    """

    def test_entrada_aceita_int_str_lista(self):
        assert ID_FILTRO.json_schema(mode="validation")["anyOf"] == [
            {"type": "integer"},
            {"type": "string"},
            {"type": "array", "items": {"anyOf": [{"type": "integer"}, {"type": "string"}]}},
            {"type": "null"},
        ]

    def test_entrada_unico_sem_lista(self):
        assert ID_FILTRO_UNICO.json_schema(mode="validation")["anyOf"] == [
            {"type": "integer"}, {"type": "string"}, {"type": "null"},
        ]

    def test_saida_e_str_ou_none(self):
        for adapter in (ID_FILTRO, ID_FILTRO_UNICO):
            assert adapter.json_schema(mode="serialization")["anyOf"] == [{"type": "string"}, {"type": "null"}]
