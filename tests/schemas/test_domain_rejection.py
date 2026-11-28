"""Valores fora do domínio dos campos dos schemas ``Input*`` levantam ``ValidationError``.

Cada caso aqui afirma que um valor fora do domínio de um campo apertado
(``Literal`` da #184 e da #207, limites de ``tamanho_pagina``, aliases de
outro tribunal da #211, combinações de filtros que o formulário do portal não
monta) levanta ``ValidationError`` em vez de ser silenciosamente repassado ao
backend, e que os valores do domínio continuam aceitos. Vale para os schemas de
tribunais e de agregadores.

Adicionar um novo aperto num schema deve vir acompanhado de um caso aqui,
de preferência como linha nova de uma das tabelas.
"""
from __future__ import annotations

import re
from typing import Any, get_args

import numpy as np
import pytest
from pydantic import BaseModel, ValidationError

from juscraper.aggregators.comunica_cnj.schemas import InputListarComunicacoesComunicaCNJ
from juscraper.aggregators.datajud.schemas import InputListarProcessosDataJud
from juscraper.aggregators.falcao.schemas import InputListarDecisoesFalcao
from juscraper.aggregators.pdpj.schemas import InputPesquisaPdpj
from juscraper.courts.stf.schemas import InputListarDecisoesSTF
from juscraper.courts.stm.schemas import InputCJSGSTM
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
from juscraper.courts.tjgo.schemas import ORGAOS_POR_INSTANCIA_E_AREA, InputCJSGTJGO
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
from juscraper.schemas.types import InteiroSemBool
from tests._helpers import load_sample
from tests.schemas._registro import schemas_mapeados

_COM_TERMO = {"pesquisa": "x"}
# No TJRN, sem termo: termo na ementa com "Sentença" ou grau "1" e recusado
# por outra regra (``test_tjrn_recusa_termo_na_ementa_sem_ementa``).
_TJRN_SEM_TERMO = {"pesquisa": ""}


def _literal(
    schema_cls: type[BaseModel],
    campo: str,
    aceitos: list[Any],
    recusados: list[Any],
    base: dict[str, Any] = _COM_TERMO,
) -> Any:
    return pytest.param(schema_cls, base, campo, aceitos, recusados, id=f"{schema_cls.__name__}.{campo}")


# Campos com domínio discreto fechado via ``Literal[...]``: (Schema, campo,
# valores aceitos, valores recusados, kwargs obrigatórios). Os da #207 trazem os
# valores dos formulários e APIs de cada tribunal; os recusados incluem a
# grafia que a docstring antiga indicava, quando ela não era a do backend.
_LITERAL_CASES = [
    _literal(InputCJSGTJMG, "order_by", [0, "2"], [99]),
    _literal(InputCJSGTJMG, "tamanho_pagina", [10, 20, 50], [99]),
    _literal(InputCJSGTJMG, "pesquisar_por", ["ementa", "acordao"], ["texto"]),
    _literal(InputCJSGTJGO, "id_area", [0, 1, 2, "2"], [99]),
    _literal(InputCJSGTJPA, "sort_order", ["asc", "desc"], ["random"]),
    _literal(InputCJSGTJTO, "ordenacao", ["ASC", "DESC", "RELEV"], ["RANDOM"]),
    _literal(InputCJSGTJTO, "tipo_documento", ["acordaos", "decisoes", "sentencas"], ["liminares"]),
    _literal(InputCJPGTJTO, "ordenacao", ["ASC", "DESC", "RELEV"], ["random"]),
    _literal(InputCJPGTJTO, "tipo_documento", ["acordaos", "decisoes", "sentencas"], ["liminares"]),
    _literal(InputCJSGTJBA, "ordenado_por", ["dataPublicacao", "relevancia"], ["dataJulgamento", "xyz"]),
    _literal(InputCJSGTJMT, "tipo_consulta", ["Acordao", "DecisaoMonocratica"], ["Decisao", "acordao"]),
    _literal(InputCJSGTJAP, "orgao", ["0", "tj", "recursal"], ["1", "turma"]),
    # "Unanime" sai do schema: o client o converte em "Unânime" com DeprecationWarning.
    _literal(InputCJSGTJAP, "votacao", ["0", "Unânime", "Maioria"], ["Unanime", "unanime", "Empate"]),
    _literal(InputCJSGTJRJ, "competencia", ["1", "2", "3", 1, 3], ["4", 9]),
    _literal(InputCJSGTJRJ, "origem", ["1", "5", 4], ["6", 0]),
    _literal(InputCJSGTJPA, "sort_by", ["datajulgamento", "datapublicacao", "relevancia"], ["dataJulgamento", "xyz"]),
    _literal(InputCJSGTJPA, "query_type", ["free", "anywords"], ["any", "anyWords"]),
    # ``buscar_em`` aceita só os valores canônicos que o portal tem. Os nomes e
    # valores antigos (``query_scope="inteiroTeor"``, ``campo="I"``,
    # ``inteiro_teor=True``) o client converte com DeprecationWarning.
    _literal(InputCJSGTJPA, "buscar_em", ["ementa", "inteiro_teor"], ["inteiroTeor", "inteiroteor", "numero"]),
    _literal(InputCJSGTJSC, "buscar_em", ["ementa", "inteiro_teor"], ["E", "I", "numero"]),
    _literal(InputCJSGSTM, "buscar_em", ["ementa", "inteiro_teor", "numero"], ["inteiroTeor", "tudo"]),
    _literal(InputListarDecisoesSTF, "buscar_em", ["ementa", "inteiro_teor"], [True, "numero"]),
    _literal(InputCJSGTJDFT, "buscar_em", ["ementa", "inteiro_teor"], [True, "numero"]),
    _literal(InputCJSGTJPB, "id_origem", ["8", "2", "8,2"], ["2,8", "1", 8]),
    # Valores do seletor "Decisoes" do portal; os da docstring antiga davam 0 resultados.
    _literal(
        InputCJSGTJRN,
        "decisoes",
        ["", "Decisão", "Acórdão", "Sentença"],
        ["Monocraticas", "Colegiadas", "Sentencas"],
        _TJRN_SEM_TERMO,
    ),
    # Valores do seletor "Jurisdicoes" do portal; os da docstring antiga davam HTTP 502/503.
    _literal(
        InputCJSGTJRN,
        "jurisdicoes",
        ["", "TJ", "TR"],
        ["Tribunal de Justica", "Turmas Recursais", "tj"],
        _TJRN_SEM_TERMO,
    ),
    # Valores do seletor "Sistema" e dos radios de grau; outros davam 0 resultados.
    _literal(InputCJSGTJRN, "sistema", ["", "PJE", "SAJ"], ["pje", "Pje", "XYZ"], _TJRN_SEM_TERMO),
    _literal(InputCJSGTJRN, "grau", ["", "1", "2"], [2, "3", "Primeiro"], _TJRN_SEM_TERMO),
    # Campos de texto do portal onde vai ``pesquisa``.
    _literal(
        InputCJSGTJRN, "buscar_em", ["ementa", "inteiro_teor"], ["inteiroTeor", "I", "numero", ""], _TJRN_SEM_TERMO
    ),
    # 2 e 3 saem do schema: o client os converte em 151 e 15 com DeprecationWarning.
    _literal(InputCJSGTJGO, "id_instancia", [0, 15, 151, "0", "151", 1], [2, "3", 16, 99]),
    _literal(InputCJSGTJGO, "id_serventia_subtipo", ["0", "14", "83", 0, 14], ["4", 99, True]),
    _literal(
        InputCJPGTJES,
        "ordenacao",
        [None, "dt_juntada desc", "dt_juntada asc", "nr_processo asc", "nr_processo desc"],
        ["data_julgamento desc", "dt_juntada", "dt_juntada DESC", "foo desc", ""],
    ),
]


@pytest.mark.parametrize(("schema_cls", "base", "campo", "aceitos", "recusados"), _LITERAL_CASES)
def test_literal_aceita_dominio_e_recusa_o_resto(schema_cls, base, campo, aceitos, recusados):
    for valor in aceitos:
        schema_cls(**base, **{campo: valor})
    for valor in recusados:
        with pytest.raises(ValidationError):
            schema_cls(**base, **{campo: valor})


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
    """Limites numéricos de ``tamanho_pagina`` além do ``ge=1`` de ``TamanhoPagina``.

    O lower bound vale para todos (zero/negativo nunca faz sentido em
    paginação) e é conferido sobre :data:`_TAMANHO_PAGINA_CASES` em
    :func:`test_tamanho_pagina_rejeita_zero`. Upper bound só onde o teto real
    do backend foi medido ao vivo (TJDFT: 40, acima disso a API responde HTTP 400).
    """

    def test_tjba_tamanho_pagina_accepts_above_default(self):
        InputCJSGTJBA(pesquisa="x", tamanho_pagina=1)
        InputCJSGTJBA(pesquisa="x", tamanho_pagina=1000)

    def test_tjdft_tamanho_pagina_rejects_above_le(self):
        InputCJSGTJDFT(pesquisa="x", tamanho_pagina=40)
        with pytest.raises(ValidationError):
            InputCJSGTJDFT(pesquisa="x", tamanho_pagina=41)


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

# Casos de ``_TAMANHO_PAGINA_CASES`` cujo schema não está em ``INPUT_SCHEMAS``,
# e por isso fora da derivação de ``test_tamanho_pagina_cases_cobre_os_schemas_mapeados``.
_TAMANHO_PAGINA_FORA_DO_MAPA = {
    # ``PdpjScraper.pesquisa`` não tem entrada em ``INPUT_SCHEMAS``.
    (InputPesquisaPdpj, "itens_por_pagina"),
}


_CASE_IDS = [case[0].__name__ for case in _TAMANHO_PAGINA_CASES]
_PARAMETRIZA_CAMPO_DE_TAMANHO = pytest.mark.parametrize(
    ("schema_cls", "campo", "base"), [case[:3] for case in _TAMANHO_PAGINA_CASES], ids=_CASE_IDS
)


#: O ``BeforeValidator`` de ``InteiroSemBool`` (``Annotated[int, BeforeValidator(...)]``).
_VALIDADOR_SEM_BOOL = get_args(InteiroSemBool)[1]


def _rejeita_bool(schema_cls: type[BaseModel], campo: str) -> bool:
    return _VALIDADOR_SEM_BOOL in schema_cls.model_fields[campo].metadata


def test_tamanho_pagina_cases_cobre_os_schemas_mapeados():
    """A tabela traz todo campo de schema mapeado com o validador que recusa ``bool``.

    O validador vem de ``InteiroSemBool`` (base de ``TamanhoPagina``), direto
    na anotação do campo; ``paginas`` (união com ``range``/``list``) fica fora.
    """
    derivados = {
        (par.schema, campo)
        for par in schemas_mapeados()
        for campo in par.schema.model_fields
        if _rejeita_bool(par.schema, campo)
    }
    tabela = {(schema_cls, campo) for schema_cls, campo, _base, _valido in _TAMANHO_PAGINA_CASES}
    assert tabela == derivados | _TAMANHO_PAGINA_FORA_DO_MAPA
    assert all(_rejeita_bool(*caso) for caso in _TAMANHO_PAGINA_FORA_DO_MAPA)


@_PARAMETRIZA_CAMPO_DE_TAMANHO
@pytest.mark.parametrize("booleano", [True, np.True_], ids=["bool", "numpy_bool"])
def test_tamanho_pagina_rejeita_booleano(schema_cls, campo, base, booleano):
    """Booleans não são tamanhos de página, apesar de ``bool`` herdar de ``int``."""
    with pytest.raises(ValidationError, match="não bool"):
        schema_cls(**base, **{campo: booleano})


@_PARAMETRIZA_CAMPO_DE_TAMANHO
def test_tamanho_pagina_rejeita_zero(schema_cls, campo, base):
    with pytest.raises(ValidationError):
        schema_cls(**base, **{campo: 0})


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
    ``extra="forbid"``. ``test_schema_contract`` confere o ``extra_forbidden``
    de todo Input mapeado com um kwarg inventado; aqui o kwarg é o alias real
    de outro tribunal.
    """

    @pytest.mark.parametrize(
        ("schema_cls", "foreign_alias"),
        _FOREIGN_ALIAS_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_foreign_alias_rejected(self, schema_cls, foreign_alias):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            schema_cls(pesquisa="x", **{foreign_alias: 10})


# (Schema, field_name) — campos da Categoria C cujo default mudou de ``""``
# para ``None``. A parametrização garante que cada tribunal afetado preserve o
# contrato não-breaking: default ``None``, e ``""`` continua aceito.
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
        ("schema_cls", "field_name"),
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_default_is_none(self, schema_cls, field_name):
        model = schema_cls(pesquisa="x")
        assert getattr(model, field_name) is None

    @pytest.mark.parametrize(
        ("schema_cls", "field_name"),
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_accepts_explicit_none(self, schema_cls, field_name):
        schema_cls(pesquisa="x", **{field_name: None})

    @pytest.mark.parametrize(
        ("schema_cls", "field_name"),
        _CAT_C_CASES,
        ids=lambda v: v.__name__ if hasattr(v, "__name__") else v,
    )
    def test_accepts_empty_string(self, schema_cls, field_name):
        schema_cls(pesquisa="x", **{field_name: ""})


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


def _tipos_do_script_tjgo() -> list[tuple[str, str, str]]:
    """``(areaId, servTipoId, codigo)`` do array ``tipos`` do script do formulário do TJGO."""
    script = load_sample("tjgo", "cjsg/consulta_jurisprudencia.js", encoding="latin-1")
    tipos = script.split("const tipos", 1)[1].split("];", 1)[0]
    return re.findall(r'"areaId": "(\d+)", "servTipoId": "(\d+)", "codigo": "(\d+)"', tipos)


def test_tjgo_id_serventia_subtipo_bate_com_o_seletor_do_projudi():
    """A lista do ``Literal`` vem do array ``tipos`` do script do formulário (#207)."""
    codigos = {"0"} | {codigo for _, _, codigo in _tipos_do_script_tjgo()}
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


def test_tjgo_orgaos_por_instancia_e_area_batem_com_o_script_do_projudi():
    """A tabela que confere as combinacoes vem do array ``tipos`` do formulario."""
    do_script: dict[tuple[str, str], set[str]] = {}
    for area, instancia, codigo in _tipos_do_script_tjgo():
        do_script.setdefault((instancia, area), set()).add(codigo)
    assert do_script == ORGAOS_POR_INSTANCIA_E_AREA


@pytest.mark.parametrize(
    "filtros",
    [
        {"id_instancia": 151, "id_area": 1},
        {"id_instancia": "151", "id_area": "2", "id_serventia_subtipo": "6"},
        {"id_instancia": 15, "id_serventia_subtipo": 66},
        {"id_instancia": 151, "id_serventia_subtipo": 14},
        # Orgaos do 1o grau so aparecem com "Todas as instancias".
        {"id_instancia": 15, "id_serventia_subtipo": 27},
        {"id_instancia": 0, "id_area": 1, "id_serventia_subtipo": 20},
        {"id_instancia": 0, "id_area": 2, "id_serventia_subtipo": 6},
    ],
)
def test_tjgo_recusa_combinacao_que_o_formulario_nao_monta(filtros):
    with pytest.raises(ValidationError, match="formulario do Projudi"):
        InputCJSGTJGO(pesquisa="x", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"id_instancia": 151, "id_serventia_subtipo": 6},
        {"id_instancia": 15, "id_area": 1, "id_serventia_subtipo": 22},
        {"id_instancia": 15, "id_area": 2, "id_serventia_subtipo": "22"},
        {"id_instancia": 0, "id_serventia_subtipo": 27},
        {"id_instancia": 0, "id_area": 2, "id_serventia_subtipo": 42},
        {"id_instancia": 0, "id_area": 1},
        # ``1`` (deprecado, fora do formulario) fica sem conferencia.
        {"id_instancia": 1, "id_area": 2, "id_serventia_subtipo": 14},
    ],
)
def test_tjgo_aceita_combinacao_que_o_formulario_monta(filtros):
    InputCJSGTJGO(pesquisa="x", **filtros)


@pytest.mark.parametrize("jurisdicoes", ["TJ", "TR"])
def test_tjrn_recusa_jurisdicao_com_primeiro_grau(jurisdicoes):
    """``"TJ"`` e ``"TR"`` so cobrem o 2o grau; com ``grau="1"`` o portal da 0 resultados."""
    with pytest.raises(ValidationError, match="2o grau"):
        InputCJSGTJRN(pesquisa="x", jurisdicoes=jurisdicoes, grau="1")


@pytest.mark.parametrize(
    "filtros",
    [
        {"jurisdicoes": "TJ", "grau": "2"},
        {"jurisdicoes": "TR", "grau": ""},
        {"jurisdicoes": "TJ", "grau": None},
        {"jurisdicoes": "", "grau": "1"},
        {"jurisdicoes": None, "grau": "1"},
    ],
)
def test_tjrn_aceita_jurisdicao_sem_primeiro_grau(filtros):
    # Sem termo, porque decisoes de 1o grau nao tem ementa, onde ``pesquisa`` busca.
    InputCJSGTJRN(pesquisa="", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença", "grau": "2"},
        {"decisoes": "Sentença", "jurisdicoes": "TJ"},
        {"decisoes": "Sentença", "jurisdicoes": "TR", "grau": ""},
        {"decisoes": "Sentença", "jurisdicoes": "TJ", "grau": "1"},
        {"decisoes": "Acórdão", "grau": "1"},
    ],
)
def test_tjrn_recusa_decisao_fora_do_seu_grau(filtros):
    """``"Sentença"`` so existe no 1o grau e ``"Acórdão"`` so no 2o; cruzadas, o portal da 0 resultados."""
    with pytest.raises(ValidationError, match="graus diferentes"):
        InputCJSGTJRN(pesquisa="x", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença", "grau": "1"},
        {"decisoes": "Sentença", "jurisdicoes": None, "grau": None},
        {"decisoes": "Acórdão", "grau": "2"},
        {"decisoes": "Acórdão", "jurisdicoes": "TJ"},
        {"decisoes": "Acórdão", "jurisdicoes": "TR"},
        {"decisoes": "Decisão", "grau": "1"},
        {"decisoes": "Decisão", "grau": "2"},
        {"decisoes": "Decisão", "jurisdicoes": "TJ"},
        {"decisoes": "Decisão", "jurisdicoes": "TR"},
    ],
)
def test_tjrn_aceita_decisao_no_seu_grau(filtros):
    # Sem termo, porque sentencas e monocraticas nao tem ementa, onde ``pesquisa`` busca.
    InputCJSGTJRN(pesquisa="", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"decisoes": "Sentença"},
        {"grau": "1"},
        {"decisoes": "Decisão", "grau": "1"},
        {"decisoes": "Decisão", "jurisdicoes": "TJ"},
        {"decisoes": "Decisão", "jurisdicoes": "TR", "grau": "2"},
        {"decisoes": "Decisão", "sistema": "PJE"},
    ],
)
def test_tjrn_recusa_termo_na_ementa_sem_ementa(filtros):
    """So os acordaos tem ementa: com termo na ementa, os demais dao 0 resultados no portal.

    Sentencas, decisoes de 1o grau e monocraticas de ``"TJ"``, ``"TR"`` ou do
    PJe nao tem ementa.
    """
    with pytest.raises(ValidationError, match="so os acordaos tem ementa"):
        InputCJSGTJRN(pesquisa="dano moral", **filtros)


@pytest.mark.parametrize("pesquisa", ["x", "A", "a dano", "de,", '"dano moral"'])
def test_tjrn_recusa_termo_com_palavra_que_o_portal_nao_ignora(pesquisa):
    """O portal so ignora preposicoes e "e"/"ou" em minusculas e sem pontuacao."""
    with pytest.raises(ValidationError, match="so os acordaos tem ementa"):
        InputCJSGTJRN(pesquisa=pesquisa, grau="1")


@pytest.mark.parametrize(
    ("pesquisa", "filtros"),
    [
        # Sem termo, ou so com palavras que o portal ignora: a busca traz tudo do filtro.
        ("", {"decisoes": "Sentença"}),
        ("   ", {"grau": "1"}),
        ("a", {"decisoes": "Sentença"}),
        ("de", {"grau": "1"}),
        ("a de para", {"decisoes": "Decisão", "jurisdicoes": "TJ"}),
        ('"a"', {"decisoes": "Decisão", "sistema": "PJE"}),
        # No inteiro teor, que sentencas e monocraticas tem.
        ("dano moral", {"decisoes": "Sentença", "buscar_em": "inteiro_teor"}),
        ("dano moral", {"grau": "1", "buscar_em": "inteiro_teor"}),
        ("dano moral", {"decisoes": "Decisão", "jurisdicoes": "TR", "buscar_em": "inteiro_teor"}),
        # Acordaos tem ementa; ha monocraticas antigas do SAJ com ementa, sem jurisdicao.
        ("dano moral", {"decisoes": "Acórdão"}),
        ("dano moral", {"decisoes": "Acórdão", "jurisdicoes": "TJ", "grau": "2"}),
        ("dano moral", {"grau": "2"}),
        ("dano moral", {"jurisdicoes": "TR"}),
        ("apelação", {"decisoes": "Decisão"}),
        ("apelação", {"decisoes": "Decisão", "grau": "2"}),
        ("apelação", {"decisoes": "Decisão", "sistema": "SAJ"}),
        ("dano moral", {"decisoes": "Acórdão", "sistema": "PJE"}),
    ],
)
def test_tjrn_aceita_termo_na_ementa_de_quem_tem(pesquisa, filtros):
    InputCJSGTJRN(pesquisa=pesquisa, **filtros)
