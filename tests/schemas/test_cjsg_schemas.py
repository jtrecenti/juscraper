"""Schema-level contract tests for cjsg pydantic models (refs #93).

Pydantic with ``extra='forbid'`` is the single source of truth for the
public ``cjsg`` API. These tests assert that:

1. Every documented parameter is accepted (with its correct default).
2. Any unknown kwarg raises ``ValidationError``.
3. Where relevant, tribunal-specific types (``baixar_sg: bool``,
   ``origem: Literal["T","R"]``) reject obviously wrong values.

The tests are pure pydantic — no HTTP, no scraper instantiation. They
complement the per-tribunal HTTP contract tests in
``tests/<sigla>/test_cjsg_contract.py``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from juscraper.courts._esaj.schemas import InputCJSGEsajPuro
from juscraper.courts.tjsp.schemas import InputCJPGTJSP, InputCJSGTJSP


class TestInputCJSGEsajPuro:
    """TJAC/TJAL/TJAM/TJCE/TJMS share this model."""

    def test_all_documented_params_accepted(self):
        model = InputCJSGEsajPuro(
            pesquisa="dano moral",
            paginas=range(1, 2),
            ementa="responsabilidade",
            numero_recurso="1000123-45.2023.8.26.0100",
            classe="Apelação Cível",
            assunto="Indenização por Dano Moral",
            comarca="São Paulo",
            orgao_julgador="1ª Câmara",
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="31/12/2024",
            data_publicacao_inicio="01/06/2024",
            data_publicacao_fim="30/06/2024",
            origem="T",
            tipo_decisao="acordao",
        )
        assert model.pesquisa == "dano moral"
        assert model.origem == "T"

    def test_defaults(self):
        model = InputCJSGEsajPuro(pesquisa="x")
        assert model.paginas is None
        assert model.origem == "T"
        assert model.tipo_decisao == "acordao"
        assert model.numero_recurso is None

    def test_unknown_kwarg_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGEsajPuro(pesquisa="x", parametro_desconhecido="y")

    def test_typo_on_known_param_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGEsajPuro(pesquisa="x", data_inicio="01/01/2024")

    def test_origem_only_accepts_T_or_R(self):
        with pytest.raises(ValidationError):
            InputCJSGEsajPuro(pesquisa="x", origem="X")

    def test_tipo_decisao_literal(self):
        with pytest.raises(ValidationError):
            InputCJSGEsajPuro(pesquisa="x", tipo_decisao="liminar")


class TestInputCJSGTJSP:
    def test_all_documented_params_accepted(self):
        model = InputCJSGTJSP(
            pesquisa="dano moral",
            paginas=range(1, 3),
            ementa="responsabilidade",
            classe="Apelação Cível",
            assunto="Indenização por Dano Moral",
            comarca="São Paulo",
            orgao_julgador="1ª Câmara",
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="31/12/2024",
            baixar_sg=False,
            tipo_decisao="monocratica",
        )
        assert model.baixar_sg is False
        assert model.tipo_decisao == "monocratica"

    def test_defaults(self):
        model = InputCJSGTJSP(pesquisa="x")
        assert model.baixar_sg is True
        assert model.tipo_decisao == "acordao"

    def test_rejects_esaj_puro_fields_that_tjsp_doesnt_have(self):
        """TJSP doesn't expose numero_recurso / data_publicacao_* — must reject."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", numero_recurso="1000123")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", data_publicacao_inicio="01/01/2024")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", origem="T")

    def test_unknown_kwarg_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", foo="bar")


class TestInputCJPGTJSP:
    def test_all_documented_params_accepted(self):
        model = InputCJPGTJSP(
            pesquisa="dano",
            paginas=range(1, 2),
            classes=["Ação Civil Pública"],
            assuntos=["Direito do Consumidor"],
            varas=["1ª Vara Cível"],
            id_processo="1000123-45.2023.8.26.0100",
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="31/12/2024",
        )
        assert model.classes == ["Ação Civil Pública"]
        assert model.id_processo == "1000123-45.2023.8.26.0100"

    def test_defaults(self):
        model = InputCJPGTJSP()
        assert model.pesquisa == ""
        assert model.classes is None
        assert model.assuntos is None
        assert model.varas is None
        assert model.id_processo is None

    def test_rejects_cjsg_fields(self):
        """cjpg has no ementa/classe-singular/comarca/orgao_julgador/baixar_sg."""
        for bad in ("ementa", "classe", "comarca", "orgao_julgador", "baixar_sg", "tipo_decisao"):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                InputCJPGTJSP(**{bad: "x"})

    def test_unknown_kwarg_rejected(self):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJPGTJSP(parametro_bobo=True)


class TestAutoChunkMixin:
    """`auto_chunk` so deve estar declarado em schemas eSAJ com teto (#130).

    Tribunais sem teto **nao devem herdar** o mixin — ``extra='forbid'`` da
    classe concreta rejeita o flag e o usuario entende que a busca nao tem
    teto a contornar (Regra 1 do #84).
    """

    def test_esaj_puro_accepts_auto_chunk(self):
        model = InputCJSGEsajPuro(pesquisa="x", auto_chunk=False)
        assert model.auto_chunk is False

    def test_esaj_puro_default_is_true(self):
        model = InputCJSGEsajPuro(pesquisa="x")
        assert model.auto_chunk is True

    def test_tjsp_cjsg_accepts_auto_chunk(self):
        model = InputCJSGTJSP(pesquisa="x", auto_chunk=False)
        assert model.auto_chunk is False

    def test_tjsp_cjpg_accepts_auto_chunk(self):
        model = InputCJPGTJSP(auto_chunk=False)
        assert model.auto_chunk is False

    def test_non_esaj_schema_rejects_auto_chunk(self):
        """Schemas sem teto rejeitam o flag (1C-a/1C-b sem o mixin)."""
        from juscraper.courts.tjpa.schemas import InputCJSGTJPA

        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJPA(pesquisa="x", auto_chunk=True)
