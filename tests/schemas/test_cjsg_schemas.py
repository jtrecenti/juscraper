"""Schema-level tests for the eSAJ search models and for ``AutoChunkMixin`` (refs #93, #130).

Pydantic with ``extra='forbid'`` is the single source of truth for the
public ``cjsg``/``cjpg`` API. For the three eSAJ models
(``InputCJSGEsajPuro``, ``InputCJSGTJSP``, ``InputCJPGEsaj``) these tests
assert that:

1. Every documented parameter is accepted, and the defaults are the documented ones.
2. Parameters of the sibling eSAJ endpoints and typos are rejected
   (``extra_forbidden``).
3. Tribunal-specific types (``origem: Literal["T","R"]``,
   ``tipo_decisao``) reject obviously wrong values.

``TestAutoChunkMixin`` covers every mapped Input: only the schemas with a
result cap inherit ``auto_chunk``. The generic "unknown kwarg raises
``extra_forbidden``" check for every mapped Input lives in
:mod:`tests.schemas.test_schema_contract`.

The tests are pure pydantic — no HTTP, no scraper instantiation. They
complement the per-tribunal HTTP contract tests in
``tests/<sigla>/test_cjsg_contract.py``.
"""
from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from juscraper.courts._esaj.schemas import InputCJPGEsaj, InputCJSGEsajPuro
from juscraper.courts.tjba.schemas import InputCJSGTJBA
from juscraper.courts.tjro.schemas import InputCJSGTJRO
from juscraper.courts.tjsp.schemas import InputCJSGTJSP
from juscraper.schemas.mixins import AutoChunkMixin
from tests.schemas._registro import payload_minimo, schemas_mapeados


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
            numero_recurso="1507541-25.2025.8.26.0425",
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
        assert model.numero_recurso == "1507541-25.2025.8.26.0425"

    def test_defaults(self):
        model = InputCJSGTJSP(pesquisa="x")
        assert model.numero_recurso is None
        assert model.baixar_sg is True
        assert model.tipo_decisao == "acordao"

    def test_rejects_esaj_puro_fields_that_tjsp_doesnt_have(self):
        """TJSP doesn't expose data_publicacao_* / origem — must reject."""
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", data_publicacao_inicio="01/01/2024")
        with pytest.raises(ValidationError, match="extra_forbidden"):
            InputCJSGTJSP(pesquisa="x", origem="T")


class TestInputCJPGEsaj:
    def test_all_documented_params_accepted(self):
        model = InputCJPGEsaj(
            pesquisa="dano",
            paginas=range(1, 2),
            classe=["Ação Civil Pública"],
            assunto=["Direito do Consumidor"],
            vara=["1ª Vara Cível"],
            id_processo="1000123-45.2023.8.26.0100",
            data_julgamento_inicio="01/01/2024",
            data_julgamento_fim="31/12/2024",
        )
        # IdFiltro colapsa lista para CSV; refs #232.
        assert model.classe == "Ação Civil Pública"
        assert model.id_processo == "1000123-45.2023.8.26.0100"

    def test_defaults(self):
        model = InputCJPGEsaj()
        assert model.pesquisa == ""
        assert model.classe is None
        assert model.assunto is None
        assert model.vara is None
        assert model.id_processo is None

    def test_rejects_cjsg_fields(self):
        """O cjpg nao tem ementa/comarca/orgao_julgador/baixar_sg.

        ``classe``/``assunto`` agora **sao** aceitos (singular canonico,
        refs #232). Os plurais ``classes``/``assuntos``/``varas`` viraram
        alias deprecados tratados na camada do client; no schema eles
        ainda sao ``extra_forbidden``.
        """
        for bad in ("ementa", "comarca", "orgao_julgador", "baixar_sg", "tipo_decisao"):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                InputCJPGEsaj(**{bad: "x"})

    def test_rejects_plural_aliases_at_schema(self):
        """Plurais sao tratados no client (deprecation); no schema sao extra_forbidden."""
        for plural in ("classes", "assuntos", "varas"):
            with pytest.raises(ValidationError, match="extra_forbidden"):
                InputCJPGEsaj(**{plural: ["x"]})


#: Classes ``Input*`` de ``INPUT_SCHEMAS``, sem repetir as compartilhadas.
_SCHEMAS_MAPEADOS_UNICOS: list[type[BaseModel]] = list(dict.fromkeys(par.schema for par in schemas_mapeados()))
_COM_AUTO_CHUNK = [schema for schema in _SCHEMAS_MAPEADOS_UNICOS if issubclass(schema, AutoChunkMixin)]
_SEM_AUTO_CHUNK = [schema for schema in _SCHEMAS_MAPEADOS_UNICOS if not issubclass(schema, AutoChunkMixin)]


class TestAutoChunkMixin:
    """O ``auto_chunk`` so deve estar declarado em schemas de busca com teto (#130).

    Tribunais sem teto **nao devem herdar** o mixin — ``extra='forbid'`` da
    classe concreta rejeita o flag e o usuario entende que a busca nao tem
    teto a contornar (Regra 1 do #84).
    """

    #: eSAJ (cjsg e cjpg) e os portais que cortam a busca em 10.000 resultados
    #: (TJBA e TJRO), onde ``auto_chunk`` divide a busca por data.
    ESPERADOS = frozenset({InputCJSGEsajPuro, InputCJSGTJSP, InputCJPGEsaj, InputCJSGTJBA, InputCJSGTJRO})

    def test_so_os_schemas_com_teto_herdam_o_mixin(self):
        """Herdar ``AutoChunkMixin`` e decisao por tribunal: entrada nova passa por aqui."""
        assert set(_COM_AUTO_CHUNK) == self.ESPERADOS

    @pytest.mark.parametrize("schema_cls", _COM_AUTO_CHUNK, ids=lambda cls: cls.__name__)
    def test_schema_com_teto_aceita_auto_chunk(self, schema_cls):
        payload = payload_minimo(schema_cls)
        assert schema_cls(**payload).auto_chunk is True
        assert schema_cls(**payload, auto_chunk=False).auto_chunk is False

    def test_schemas_sem_teto_rejeitam_auto_chunk(self):
        """Todo Input mapeado sem o mixin recusa o flag (1C-a/1C-b sem o mixin)."""
        assert _SEM_AUTO_CHUNK
        for schema_cls in _SEM_AUTO_CHUNK:
            with pytest.raises(ValidationError, match="extra_forbidden"):
                schema_cls(**payload_minimo(schema_cls), auto_chunk=True)
