"""Domain rejection tests for tightened cjsg/cjpg schemas (refs #184).

Cada caso aqui afirma que valor fora do domínio fechado de um campo apertado
pela #184 levanta ``ValidationError`` em vez de ser silenciosamente repassado
ao backend. A rede de segurança fecha o gap identificado durante o
planejamento da #184: até a virada, ``test_cjsg_schemas.py`` só cobria 2
casos manuais (``origem`` e ``tipo_decisao`` da família eSAJ-puro).

Os casos abaixo seguem o padrão de
``test_cjsg_schemas.py::TestInputCJSGEsajPuro::test_origem_only_accepts_T_or_R``.
Cada bloco exercita um schema concreto com 1-2 valores inválidos
representativos. Adicionar um novo aperto na #184 (ou follow-up) deve vir
acompanhado de um caso aqui.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from juscraper.courts.tjba.schemas import InputCJSGTJBA
from juscraper.courts.tjdft.schemas import InputCJSGTJDFT
from juscraper.courts.tjes.schemas import InputCJPGTJES, InputCJSGTJES
from juscraper.courts.tjgo.schemas import InputCJSGTJGO
from juscraper.courts.tjmg.schemas import InputCJSGTJMG
from juscraper.courts.tjmt.schemas import InputCJSGTJMT
from juscraper.courts.tjpa.schemas import InputCJSGTJPA
from juscraper.courts.tjpb.schemas import InputCJSGTJPB
from juscraper.courts.tjpi.schemas import InputCJSGTJPI
from juscraper.courts.tjrn.schemas import InputCJSGTJRN
from juscraper.courts.tjro.schemas import InputCJSGTJRO
from juscraper.courts.tjrr.schemas import InputCJSGTJRR
from juscraper.courts.tjsc.schemas import InputCJSGTJSC
from juscraper.courts.tjto.schemas import InputCJPGTJTO, InputCJSGTJTO


class TestLiteralRejection:
    """Categoria A — campos com domínio discreto fechado via ``Literal[...]``."""

    def test_tjmg_order_by_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMG(pesquisa="x", order_by=99)

    def test_tjmg_order_by_accepts_int_and_str(self):
        InputCJSGTJMG(pesquisa="x", order_by=0)
        InputCJSGTJMG(pesquisa="x", order_by="2")

    def test_tjmg_tamanho_pagina_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMG(pesquisa="x", tamanho_pagina=99)

    def test_tjmg_pesquisar_por_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMG(pesquisa="x", pesquisar_por="texto")

    def test_tjgo_id_instancia_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJGO(pesquisa="x", id_instancia=99)

    def test_tjgo_id_area_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJGO(pesquisa="x", id_area=99)

    def test_tjpa_sort_order_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJPA(pesquisa="x", sort_order="random")

    def test_tjpa_sort_order_accepts_canonical(self):
        InputCJSGTJPA(pesquisa="x", sort_order="asc")
        InputCJSGTJPA(pesquisa="x", sort_order="desc")

    def test_tjto_ordenacao_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJTO(pesquisa="x", ordenacao="RANDOM")

    def test_tjto_ordenacao_accepts_canonical(self):
        for valor in ("ASC", "DESC", "RELEV"):
            InputCJSGTJTO(pesquisa="x", ordenacao=valor)

    def test_tjto_tipo_documento_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJTO(pesquisa="x", tipo_documento="liminares")

    def test_tjto_cjpg_inherits_same_literal(self):
        with pytest.raises(ValidationError):
            InputCJPGTJTO(pesquisa="x", ordenacao="random")
        with pytest.raises(ValidationError):
            InputCJPGTJTO(pesquisa="x", tipo_documento="liminares")


class TestNumericFieldRejection:
    """Categoria B — lower bound numérico via ``Field(ge=1)``.

    Apenas o lower bound é fiscalizado (zero/negativo nunca faz sentido em
    paginação). Upper bound não é apertado neste PR — exige captura ao vivo
    do backend para definir o teto real, encaminhada em issue follow-up.
    """

    def test_tjba_tamanho_pagina_rejects_below_ge(self):
        with pytest.raises(ValidationError):
            InputCJSGTJBA(pesquisa="x", tamanho_pagina=0)

    def test_tjba_tamanho_pagina_accepts_above_default(self):
        InputCJSGTJBA(pesquisa="x", tamanho_pagina=1)
        InputCJSGTJBA(pesquisa="x", tamanho_pagina=1000)

    def test_tjdft_tamanho_pagina_rejects_below_ge(self):
        with pytest.raises(ValidationError):
            InputCJSGTJDFT(pesquisa="x", tamanho_pagina=0)

    def test_tjes_tamanho_pagina_rejects_below_ge_in_cjsg_and_cjpg(self):
        with pytest.raises(ValidationError):
            InputCJSGTJES(pesquisa="x", tamanho_pagina=0)
        with pytest.raises(ValidationError):
            InputCJPGTJES(pesquisa="x", tamanho_pagina=0)

    def test_tjgo_tamanho_pagina_rejects_below_ge(self):
        with pytest.raises(ValidationError):
            InputCJSGTJGO(pesquisa="x", tamanho_pagina=0)

    def test_tjmt_tamanho_pagina_rejects_below_ge(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMT(pesquisa="x", tamanho_pagina=0)


# (Schema, field_name) — campos da Categoria C cujo default mudou de ``""``
# para ``None``. A parametrização garante que cada um dos 8 tribunais
# afetados preserve o contrato não-breaking: default ``None``, e ``""``
# continua aceito.
_CAT_C_CASES = [
    (InputCJSGTJGO, "numero_processo"),
    (InputCJSGTJPB, "numero_processo"),
    (InputCJSGTJPB, "id_classe"),
    (InputCJSGTJPB, "id_orgao_julgador"),
    (InputCJSGTJPB, "id_relator"),
    (InputCJSGTJRN, "numero_processo"),
    (InputCJSGTJRN, "id_classe"),
    (InputCJSGTJRN, "id_orgao_julgador"),
    (InputCJSGTJRN, "id_relator"),
    (InputCJSGTJRN, "id_colegiado"),
    (InputCJSGTJRN, "sistema"),
    (InputCJSGTJRN, "decisoes"),
    (InputCJSGTJRN, "jurisdicoes"),
    (InputCJSGTJRN, "grau"),
    (InputCJSGTJPI, "tipo"),
    (InputCJSGTJPI, "relator"),
    (InputCJSGTJPI, "classe"),
    (InputCJSGTJPI, "orgao"),
    (InputCJSGTJRO, "numero_processo"),
    (InputCJSGTJRO, "relator"),
    (InputCJSGTJRO, "classe"),
    (InputCJSGTJTO, "numero_processo"),
    (InputCJPGTJTO, "numero_processo"),
    (InputCJSGTJSC, "processo"),
    (InputCJSGTJRR, "relator"),
]


class TestOptionalSentinelAcceptance:
    """Categoria C — ``str = ""`` → ``str | None = None``.

    Garante que (a) ``None`` é o default novo; (b) ``None`` explícito é
    aceito; (c) string vazia continua sendo aceita (não-breaking — quem
    passava ``""`` explícito segue funcionando).
    """

    @pytest.mark.parametrize(
        "schema_cls,field_name",
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_default_is_none(self, schema_cls, field_name):
        model = schema_cls(pesquisa="x")
        assert getattr(model, field_name) is None

    @pytest.mark.parametrize(
        "schema_cls,field_name",
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_accepts_explicit_none(self, schema_cls, field_name):
        schema_cls(pesquisa="x", **{field_name: None})

    @pytest.mark.parametrize(
        "schema_cls,field_name",
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_accepts_empty_string(self, schema_cls, field_name):
        schema_cls(pesquisa="x", **{field_name: ""})


class TestTJROOrgaoJulgadorIntZero:
    """TJRO ``orgao_julgador`` aceita ``int | str | None`` — ``0`` (int) deve
    ser preservado intacto, não confundido com ``None`` nem com ``""``.

    Protege o ternário ``inp.orgao_julgador if inp.orgao_julgador is not None
    else ""`` no client (o ingênuo ``or ""`` quebraria o caso).
    """

    def test_orgao_julgador_zero_int_preserved(self):
        inp = InputCJSGTJRO(pesquisa="x", orgao_julgador=0)
        assert inp.orgao_julgador == 0
        assert inp.orgao_julgador is not None

    def test_orgao_julgador_colegiado_zero_int_preserved(self):
        inp = InputCJSGTJRO(pesquisa="x", orgao_julgador_colegiado=0)
        assert inp.orgao_julgador_colegiado == 0
        assert inp.orgao_julgador_colegiado is not None
