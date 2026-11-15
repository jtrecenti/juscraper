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

import re
from typing import get_args

import numpy as np
import pytest
from pydantic import ValidationError

from juscraper.aggregators.comunica_cnj.schemas import InputListarComunicacoesComunicaCNJ
from juscraper.aggregators.datajud.schemas import InputListarProcessosDataJud
from juscraper.aggregators.falcao.schemas import InputListarDecisoesFalcao
from juscraper.aggregators.pdpj.schemas import InputPesquisaPdpj
from juscraper.courts.stf.schemas import InputListarDecisoesSTF
from juscraper.courts.tjap.schemas import InputCJSGTJAP
from juscraper.courts.tjba.schemas import InputCJSGTJBA
from juscraper.courts.tjdft.schemas import InputCJSGTJDFT
from juscraper.courts.tjes.schemas import (
    ORDENACOES_POR_CORE,
    InputCJPGTJES,
    InputCJSGTJES,
    OrdenacaoCJPG,
    OrdenacaoCJSG,
)
from juscraper.courts.tjgo.schemas import InputCJSGTJGO
from juscraper.courts.tjmg.schemas import InputCJSGTJMG
from juscraper.courts.tjmt.schemas import InputCJSGTJMT
from juscraper.courts.tjpa.schemas import InputCJSGTJPA
from juscraper.courts.tjpb.schemas import InputCJSGTJPB
from juscraper.courts.tjpi.schemas import InputCJSGTJPI
from juscraper.courts.tjrj.download import extract_select_options
from juscraper.courts.tjrj.schemas import InputCJSGTJRJ
from juscraper.courts.tjrn.schemas import InputCJSGTJRN
from juscraper.courts.tjro.schemas import InputCJSGTJRO
from juscraper.courts.tjsc.schemas import InputCJSGTJSC
from juscraper.courts.tjto.schemas import InputCJPGTJTO, InputCJSGTJTO
from tests._helpers import load_sample


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


# (Schema, campo, valores aceitos, valores recusados) — campos apertados na #207
# com os valores dos formulários e APIs de cada tribunal. Os recusados incluem a
# grafia que a docstring antiga indicava, quando ela não era a do backend.
_LITERAL_207_CASES = [
    (InputCJSGTJBA, "ordenado_por", ["dataPublicacao", "relevancia"], ["dataJulgamento", "xyz"]),
    (InputCJSGTJMT, "tipo_consulta", ["Acordao", "DecisaoMonocratica"], ["Decisao", "acordao"]),
    (InputCJSGTJAP, "orgao", ["0", "tj", "recursal"], ["1", "turma"]),
    # "Unanime" sai do schema: o client o converte em "Unânime" com DeprecationWarning.
    (InputCJSGTJAP, "votacao", ["0", "Unânime", "Maioria"], ["Unanime", "unanime", "Empate"]),
    (InputCJSGTJRJ, "competencia", ["1", "2", "3", 1, 3], ["4", 9]),
    (InputCJSGTJRJ, "origem", ["1", "5", 4], ["6", 0]),
    (InputCJSGTJPA, "sort_by", ["datajulgamento", "datapublicacao", "relevancia"], ["dataJulgamento", "xyz"]),
    (InputCJSGTJPA, "query_type", ["free", "anywords"], ["any", "anyWords"]),
    (InputCJSGTJPA, "query_scope", ["ementa", "inteiroTeor", "inteiroteor"], ["integra", "xyz"]),
    (InputCJSGTJPB, "id_origem", ["8", "2", "8,2"], ["2,8", "1", 8]),
    # 2 e 3 saem do schema: o client os converte em 151 e 15 com DeprecationWarning.
    (InputCJSGTJGO, "id_instancia", [0, 15, 151, "0", "151", 1], [2, "3", 16]),
    (InputCJSGTJGO, "id_serventia_subtipo", ["0", "14", "83", 0, 14], ["4", 99, True]),
    (
        InputCJPGTJES,
        "ordenacao",
        [None, "dt_juntada desc", "dt_juntada asc", "nr_processo asc", "nr_processo desc"],
        ["data_julgamento desc", "dt_juntada", "dt_juntada DESC", "foo desc", ""],
    ),
]


@pytest.mark.parametrize(
    "schema_cls, campo, aceitos, recusados",
    _LITERAL_207_CASES,
    ids=[f"{c[0].__name__}.{c[1]}" for c in _LITERAL_207_CASES],
)
def test_literal_207_aceita_dominio_e_recusa_o_resto(schema_cls, campo, aceitos, recusados):
    for valor in aceitos:
        schema_cls(pesquisa="x", **{campo: valor})
    for valor in recusados:
        with pytest.raises(ValidationError):
            schema_cls(pesquisa="x", **{campo: valor})


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


def test_tjgo_id_serventia_subtipo_int_vira_string():
    assert InputCJSGTJGO(pesquisa="x", id_serventia_subtipo=14).id_serventia_subtipo == "14"
    assert InputCJSGTJGO(pesquisa="x").id_serventia_subtipo == "0"


class TestNumericFieldRejection:
    """Categoria B — lower bound numérico via ``Field(ge=1)``.

    O lower bound vale para todos (zero/negativo nunca faz sentido em
    paginação). Upper bound só onde o teto real do backend foi medido ao vivo
    (TJDFT: 40, acima disso a API responde HTTP 400).
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

    def test_tjdft_tamanho_pagina_rejects_above_le(self):
        InputCJSGTJDFT(pesquisa="x", tamanho_pagina=40)
        with pytest.raises(ValidationError):
            InputCJSGTJDFT(pesquisa="x", tamanho_pagina=41)

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


# (Schema, campo, kwargs obrigatórios, valor válido) — todo campo de tamanho de
# página tipado como ``TamanhoPagina`` ou ``InteiroSemBool`` (Falcão). O valor válido respeita o domínio
# próprio do endpoint (DataJud: 10 a 10000; Falcão: 5 ou 10).
_TAMANHO_PAGINA_CASES = [
    (InputCJSGTJBA, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputCJSGTJDFT, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputCJSGTJES, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputCJPGTJES, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputCJSGTJGO, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputCJSGTJMT, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputListarDecisoesSTF, "tamanho_pagina", {"pesquisa": "x"}, 2),
    (InputListarDecisoesFalcao, "tamanho_pagina", {"pesquisa": "x"}, 5),
    (InputListarProcessosDataJud, "tamanho_pagina", {}, 20),
    (InputListarComunicacoesComunicaCNJ, "itens_por_pagina", {"pesquisa": "x"}, 2),
    (InputPesquisaPdpj, "itens_por_pagina", {}, 2),
]


_CASE_IDS = [case[0].__name__ for case in _TAMANHO_PAGINA_CASES]


@pytest.mark.parametrize(
    ("schema_cls", "campo", "base"), [case[:3] for case in _TAMANHO_PAGINA_CASES], ids=_CASE_IDS
)
@pytest.mark.parametrize("booleano", [True, np.True_], ids=["bool", "numpy_bool"])
def test_tamanho_pagina_rejeita_booleano(schema_cls, campo, base, booleano):
    """Booleans não são tamanhos de página, apesar de ``bool`` herdar de ``int``."""
    with pytest.raises(ValidationError, match="não bool"):
        schema_cls(**base, **{campo: booleano})


@pytest.mark.parametrize(("schema_cls", "campo", "base", "valido"), _TAMANHO_PAGINA_CASES, ids=_CASE_IDS)
def test_tamanho_pagina_aceita_inteiro_e_string_numerica(schema_cls, campo, base, valido):
    assert getattr(schema_cls(**base, **{campo: valido}), campo) == valido
    assert getattr(schema_cls(**base, **{campo: str(valido)}), campo) == valido


# (Schema, foreign_alias) — cada schema testado contra um alias de
# tamanho_pagina que pertence a outro tribunal. A invariante é "cada
# client conhece só o seu alias" (refs #211): TJBA aceita
# ``items_per_page`` mas não ``linhas_por_pagina``; este último cai em
# ``ValidationError`` via ``extra="forbid"`` no schema, traduzido pelo
# client em ``TypeError`` na API pública.
_FOREIGN_ALIAS_CASES = [
    (InputCJSGTJBA, "linhas_por_pagina"),
    (InputCJSGTJDFT, "items_per_page"),
    (InputCJSGTJES, "qtde_itens_pagina"),
    (InputCJPGTJES, "qtde_itens_pagina"),
    (InputCJSGTJGO, "per_page"),
    (InputCJSGTJMG, "quantidade_por_pagina"),
    (InputCJSGTJMT, "linhas_por_pagina"),
]


class TestCrossTribunalAliasRejection:
    """Cross-tribunal alias rejection (refs #211).

    Cada tribunal deprecou exatamente um alias para ``tamanho_pagina`` —
    o nome histórico do seu backend específico. Passar o alias de outro
    tribunal não é uma migração válida, e o schema rejeita via
    ``extra="forbid"``.
    """

    @pytest.mark.parametrize(
        "schema_cls,foreign_alias",
        _FOREIGN_ALIAS_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_foreign_alias_rejected(self, schema_cls, foreign_alias):
        with pytest.raises(ValidationError):
            schema_cls(pesquisa="x", **{foreign_alias: 10})


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


def test_tjgo_id_serventia_subtipo_bate_com_o_seletor_do_projudi():
    """A lista do ``Literal`` vem do array ``tipos`` do script do formulário (#207)."""
    script = load_sample("tjgo", "cjsg/consulta_jurisprudencia.js", encoding="latin-1")
    tipos = script.split("const tipos", 1)[1].split("];", 1)[0]
    codigos = {"0"} | set(re.findall(r'"codigo": "(\d+)"', tipos))
    campo = InputCJSGTJGO.model_fields["id_serventia_subtipo"].annotation
    assert set(get_args(campo)) == codigos


def test_tjgo_id_instancia_bate_com_o_seletor_do_projudi():
    """O ``Literal`` traz as opções do seletor "Instância" do formulário atual.

    ``1`` (1º grau) fica fora da comparação: deprecado, segue aceito até a 0.7.0.
    """
    html = load_sample("tjgo", "cjsg/blocked_turnstile.html", encoding="latin-1")
    select = re.search(r'<select id="Id_Instancia".*?</select>', html, re.S)
    assert select is not None
    opcoes = set(re.findall(r'<option value="(\d+)"', select.group(0)))
    aceitos = {str(v) for v in get_args(InputCJSGTJGO.model_fields["id_instancia"].annotation)}
    assert aceitos - {"1"} == opcoes


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
