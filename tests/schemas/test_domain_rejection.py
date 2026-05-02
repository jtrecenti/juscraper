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
from juscraper.courts.tjto.schemas import InputCJPGTJTO, InputCJSGTJTO


class TestLiteralRejection:
    """Categoria A — campos com domínio discreto fechado via ``Literal[...]``."""

    def test_tjmg_order_by_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMG(pesquisa="x", order_by=99)

    def test_tjmg_order_by_accepts_int_and_str(self):
        InputCJSGTJMG(pesquisa="x", order_by=0)
        InputCJSGTJMG(pesquisa="x", order_by="2")

    def test_tjmg_linhas_por_pagina_rejects_out_of_domain(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMG(pesquisa="x", linhas_por_pagina=99)

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
    """Categoria B — limites numéricos via ``Field(ge=, le=)``."""

    def test_tjba_items_per_page_rejects_above_le(self):
        with pytest.raises(ValidationError):
            InputCJSGTJBA(pesquisa="x", items_per_page=999)

    def test_tjba_items_per_page_rejects_below_ge(self):
        with pytest.raises(ValidationError):
            InputCJSGTJBA(pesquisa="x", items_per_page=0)

    def test_tjba_items_per_page_accepts_within_range(self):
        InputCJSGTJBA(pesquisa="x", items_per_page=1)
        InputCJSGTJBA(pesquisa="x", items_per_page=100)

    def test_tjdft_quantidade_por_pagina_rejects_above_le(self):
        with pytest.raises(ValidationError):
            InputCJSGTJDFT(pesquisa="x", quantidade_por_pagina=999)

    def test_tjes_per_page_rejects_above_le_in_cjsg_and_cjpg(self):
        with pytest.raises(ValidationError):
            InputCJSGTJES(pesquisa="x", per_page=999)
        with pytest.raises(ValidationError):
            InputCJPGTJES(pesquisa="x", per_page=999)

    def test_tjes_per_page_rejects_below_ge_in_cjsg_and_cjpg(self):
        with pytest.raises(ValidationError):
            InputCJSGTJES(pesquisa="x", per_page=0)
        with pytest.raises(ValidationError):
            InputCJPGTJES(pesquisa="x", per_page=0)

    def test_tjgo_qtde_itens_pagina_rejects_above_le(self):
        with pytest.raises(ValidationError):
            InputCJSGTJGO(pesquisa="x", qtde_itens_pagina=999)

    def test_tjmt_quantidade_por_pagina_rejects_above_le(self):
        with pytest.raises(ValidationError):
            InputCJSGTJMT(pesquisa="x", quantidade_por_pagina=999)


class TestOptionalSentinelAcceptance:
    """Categoria C — ``str = ""`` → ``str | None = None``.

    Garante que (a) ``None`` é aceito como default novo; (b) string vazia
    continua sendo aceita (não-breaking — quem passava ``""`` explícito
    segue funcionando).
    """

    def test_tjgo_numero_processo_accepts_none_and_empty(self):
        InputCJSGTJGO(pesquisa="x")  # default agora é None
        InputCJSGTJGO(pesquisa="x", numero_processo=None)
        InputCJSGTJGO(pesquisa="x", numero_processo="")

    def test_tjgo_numero_processo_default_is_none(self):
        model = InputCJSGTJGO(pesquisa="x")
        assert model.numero_processo is None
