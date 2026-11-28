"""Valores fora do domínio dos campos dos schemas ``Input*`` levantam ``ValidationError``.

Cada caso aqui afirma que um valor fora do domínio de um campo apertado
(``Literal`` da #184 e da #207, limites de ``tamanho_pagina``, aliases de
outro tribunal da #211) levanta ``ValidationError`` em vez de ser silenciosamente
repassado ao backend, e que os valores do domínio continuam aceitos. Vale para os
schemas de tribunais e de agregadores.

Adicionar um novo aperto num schema deve vir acompanhado de um caso aqui,
como linha nova de uma das tabelas. Regra de um tribunal só (combinações de
filtros que o formulário do portal não monta, opções conferidas contra o HTML
do portal) fica em ``tests/<sigla>/test_cjsg_schema.py``.
"""
from __future__ import annotations

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
from juscraper.courts.tjes.schemas import InputCJPGTJES, InputCJSGTJES
from juscraper.courts.tjgo.schemas import InputCJSGTJGO
from juscraper.courts.tjmg.schemas import InputCJSGTJMG
from juscraper.courts.tjmt.schemas import InputCJSGTJMT
from juscraper.courts.tjpa.schemas import InputCJSGTJPA
from juscraper.courts.tjpb.schemas import InputCJSGTJPB
from juscraper.courts.tjpi.schemas import InputCJSGTJPI
from juscraper.courts.tjrj.schemas import InputCJSGTJRJ
from juscraper.courts.tjrn.schemas import InputCJSGTJRN
from juscraper.courts.tjro.schemas import InputCJSGTJRO
from juscraper.courts.tjsc.schemas import InputCJSGTJSC
from juscraper.courts.tjto.schemas import InputCJPGTJTO, InputCJSGTJTO
from juscraper.schemas.types import InteiroSemBool
from tests.schemas._registro import schemas_mapeados

_COM_TERMO = {"pesquisa": "x"}
# No TJRN, sem termo: termo na ementa com "Sentença" ou grau "1" e recusado
# por outra regra (``tests/tjrn/test_cjsg_schema.py``).
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
    assert tabela == derivados


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
