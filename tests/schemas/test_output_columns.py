"""Colunas que os parsers entregam sobre os samples reais (#12, #717).

:mod:`tests.schemas.test_canonical_types` e :mod:`tests.schemas.test_output_parity`
olham só os campos **declarados** nos ``Output*`` e o código-fonte do parser.
Como os ``Output*`` têm ``extra="allow"``, uma coluna que o parser entrega sem
declarar passa pelos dois: foi assim que ``relatora`` (``cjsg`` do eSAJ, #717)
e ``magistrado`` (``cjpg`` do eSAJ) escaparam, embora ``magistrado`` já
estivesse em :data:`DEPRECATED_SYNONYMS`. Os parsers que montam a chave a
partir do rótulo do HTML (eSAJ) ou repassam o JSON da API nem passam pela
conferência por substring de ``test_output_parity``.

Aqui, o parser público de cada endpoint de
:data:`tests.schemas._registro.OUTPUT_SCHEMAS` roda sobre os arquivos de
``tests/<sigla>/samples/<pasta>/``, e as colunas **efetivamente entregues**
passam por duas conferências:

1. Nenhuma coluna tem nome de :data:`DEPRECATED_SYNONYMS` (todos os endpoints).
2. Toda coluna está declarada no ``Output*`` do endpoint, ou em
   :data:`AUXILIARES_NAO_DECLARADAS` com motivo. Os endpoints de
   :data:`SO_NOMES_DEPRECADOS`, que repassam o JSON do backend, ficam só com a
   conferência 1: lá ``extra="allow"`` é o contrato e declarar cada chave da API
   não traria garantia.

A conferência 2 pega o sinônimo que ainda não está na lista: um rótulo novo
do portal que vira coluna nova falha o teste até alguém declará-la ou
renomeá-la para o nome canônico.

Sample novo entra sozinho. Arquivo da pasta que não é página de resultado
(formulário, captcha, resposta de outro endpoint) ou que foi escrito à mão com
rótulos inventados vai em ``Leitura.ignorar`` com motivo; arquivo que o parser
não lê e não está ali reprova o teste.

Sinônimo deprecado que ainda sai do parser fica em :data:`SINONIMOS_TOLERADOS`,
com o PR que o renomeia ou a decisão de API pendente; o teste de órfãos cobra
a remoção da entrada quando a coluna some dos samples.
"""
from __future__ import annotations

import fnmatch
import json
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

import juscraper as jus
from juscraper.aggregators.comunica_cnj.parse import parse_items
from juscraper.aggregators.datajud.parse import parse_datajud_api_response
from juscraper.aggregators.falcao.parse import parse_documentos
from juscraper.aggregators.jusbr.parse import parse_process_details_response
from juscraper.aggregators.pdpj.parse import build_processo_row
from juscraper.courts.stf.parse import parse_contagem, parse_decisoes
from tests.schemas._registro import OUTPUT_SCHEMAS, resolve
from tests.schemas.test_canonical_types import DEPRECATED_SYNONYMS

TESTS = Path(__file__).resolve().parent.parent
CNJ_FICTICIO = "0000000-00.0000.0.00.0000"


def _texto(arquivo: Path) -> str:
    """Samples em UTF-8 ou, como os portais que servem ISO-8859-1 os gravam, em latin-1."""
    bruto = arquivo.read_bytes()
    try:
        return bruto.decode("utf-8")
    except UnicodeDecodeError:
        return bruto.decode("iso-8859-1")


def _json(arquivo: Path) -> Any:
    return json.loads(_texto(arquivo))


def _caminho(arquivo: Path) -> tuple:
    """``(path,)``: o eSAJ e o ``cpopg``/``cposg`` do TJSP leem o arquivo baixado."""
    return (str(arquivo),)


def _paginas(arquivo: Path) -> tuple:
    """``([pagina],)``: HTML como texto, JSON decodificado."""
    if arquivo.suffix != ".json":
        return ([_texto(arquivo)],)
    return ([_json(arquivo)],)


def _json_solto(arquivo: Path) -> tuple:
    return (_json(arquivo),)


def _xhr_tjrj(arquivo: Path) -> tuple:
    """O download do TJRJ desembrulha o ``d`` do JSON do ASP.NET antes do parser."""
    return ([_json(arquivo)["d"]],)


def _detalhe_com_cnj(arquivo: Path) -> tuple:
    """``([html], [cnj])`` do ``cpopg_parse`` do PJe (TRF1, TRF5, TJPE) e do eproc (TRF6)."""
    return ([_texto(arquivo)], [CNJ_FICTICIO])


def _registros_tjdft(arquivo: Path) -> tuple:
    """O download do TJDFT entrega a lista ``registros`` de cada página ao parser."""
    return (_json(arquivo)["registros"],)


def _resultado_tjmg(arquivo: Path) -> tuple:
    """Só a página de resultado; as de partes viram a coluna ``partes``, que fica ``None``."""
    return ([{"id_cnj": CNJ_FICTICIO, "resultado": _texto(arquivo)}],)


def _colecao_falcao(arquivo: Path) -> tuple:
    """O prefixo do nome do sample é a coleção consultada (``acordaos_normal.json``)."""
    return (_json(arquivo), arquivo.stem.split("_")[0])


def _resposta_comunica_cnj(arquivo: Path) -> tuple:
    dados = _json(arquivo)
    return (SimpleNamespace(json=lambda: dados),)


def _detalhes_jusbr(arquivo: Path) -> tuple:
    return (_json(arquivo), CNJ_FICTICIO)


def _linha_jusbr(dados: Any, cnj: str) -> list[dict]:
    return [parse_process_details_response(dados, cnj)]


def _linhas_pdpj(dados: list[dict[str, Any]], cnj: str) -> list[dict]:
    return [build_processo_row(detalhe, cnj) for detalhe in dados]


def _decisoes_stf(resposta: dict[str, Any]) -> list[dict[str, Any]]:
    decisoes: list[dict[str, Any]] = parse_decisoes([resposta])
    return decisoes


@dataclass(frozen=True)
class Leitura:
    """Como o parser de um endpoint lê um arquivo de sample.

    ``entrada(arquivo)`` monta os argumentos posicionais de ``parser``; sem
    ``parser``, vale o público ``<endpoint>_parse`` do raspador. O resultado é
    DataFrame, lista de dicts ou dict de DataFrames (o ``cpopg`` do TJSP).
    ``ignorar`` mapeia padrões ``fnmatch`` do nome do arquivo ao motivo de
    ficarem de fora.
    """

    entrada: Callable[[Path], tuple] = _paginas
    parser: Callable[..., Any] | None = None
    pasta: str | None = None
    sufixos: tuple[str, ...] = (".html", ".json")
    ignorar: Mapping[str, str] = field(default_factory=dict)


_ESAJ_CJSG = Leitura(_caminho)
_PAGINAS = Leitura()
_MOTIVO_PJE_PIVOT = "o Output cobre só o pivot (id_cnj); o detalhe do PJe vem descrito no docstring"
_PJE_CPOPG_BUSCA = {
    "form_initial.html": "formulário de busca, não chega ao parser",
    "search_*.html": "lista de busca, lida no download para achar o detalhe",
}
_PJE_CPOPG = Leitura(
    _detalhe_com_cnj,
    ignorar={
        **_PJE_CPOPG_BUSCA,
        "movs_page_*.html": "página extra de movimentações, juntada ao detalhe no download",
    },
)

LEITURAS: dict[tuple[str, str], Leitura] = {
    ("tjac", "cjsg"): _ESAJ_CJSG,
    ("tjal", "cjsg"): _ESAJ_CJSG,
    ("tjam", "cjsg"): _ESAJ_CJSG,
    ("tjce", "cjsg"): _ESAJ_CJSG,
    ("tjms", "cjsg"): _ESAJ_CJSG,
    ("tjsp", "cjsg"): _ESAJ_CJSG,
    ("tjsp", "cjpg"): Leitura(_caminho, sufixos=(".html",)),
    ("tjms", "cjpg"): Leitura(
        _caminho,
        sufixos=(".html",),
        ignorar={"pasta_*.html": "pasta digital de um processo, lida por outro endpoint"},
    ),
    ("tjsp", "cpopg"): Leitura(
        _caminho,
        ignorar={
            "search*.html": "lista de busca, lida no download para achar o processo",
            "movimentacoes_pagina_*.html": "página extra de movimentações, juntada no download",
        },
    ),
    ("tjsp", "cposg"): Leitura(
        _caminho,
        ignorar={
            "search*.html": "lista de busca, lida no download para achar o processo",
            "open.html": "redirecionamento do eSAJ, lido no download",
            "movimentacoes_pagina_*.html": "página extra de movimentações, juntada no download",
        },
    ),
    ("tjap", "cjsg"): Leitura(
        ignorar={
            "security_check_failed.json": "recusa do portal, que o parser levanta de propósito",
        },
    ),
    ("tjba", "cjsg"): _PAGINAS,
    ("tjdft", "cjsg"): Leitura(_registros_tjdft),
    ("tjes", "cjsg"): _PAGINAS,
    ("tjes", "cjpg"): _PAGINAS,
    ("tjgo", "cjsg"): Leitura(
        sufixos=(".html",),
        ignorar={"blocked_turnstile.html": "desafio anti-bot, sem resultado"},
    ),
    ("tjmg", "cjsg"): Leitura(
        sufixos=(".html",),
        ignorar={
            "categorizada*.html": "busca categorizada, que o parser recusa de propósito",
            "erro_ora.html": "erro do portal, que o parser levanta de propósito",
            "muitos_resultados.html": "aviso de muitos resultados, que o parser levanta de propósito",
            "form_acordao.html": "formulário de busca, não chega ao parser",
        },
    ),
    ("tjmg", "cposg"): Leitura(
        _resultado_tjmg,
        sufixos=(".html",),
        ignorar={"partes_*.html": "página de partes, lida junto com o resultado (coluna partes)"},
    ),
    ("tjmt", "cjsg"): _PAGINAS,
    ("tjpa", "cjsg"): _PAGINAS,
    ("tjpb", "cjsg"): _PAGINAS,
    ("tjpe", "cjsg"): Leitura(
        sufixos=(".html", ".xml"),
        ignorar={
            "step_01_consulta.html": "formulário de busca, não chega ao parser",
            "step_02_escolha.html": "escolha de tipo de decisão, não chega ao parser",
        },
    ),
    ("tjpi", "cjsg"): _PAGINAS,
    ("stm", "cjsg"): Leitura(
        sufixos=(".html",),
        ignorar={"waf_rejected.html": "recusa do WAF, que o parser levanta de propósito"},
    ),
    ("tjpr", "cjsg"): Leitura(
        sufixos=(".html",),
        ignorar={
            "home.html": "página inicial, não chega ao parser",
            "pagina_intranet.html": "página da intranet, que o parser recusa de propósito",
        },
    ),
    ("tjrj", "cjsg"): Leitura(_xhr_tjrj, sufixos=(".json",)),
    ("tjrn", "cjsg"): _PAGINAS,
    ("tjro", "cjsg"): _PAGINAS,
    ("tjrr", "cjsg"): Leitura(
        sufixos=(".html", ".xml"),
        ignorar={
            "step_01_consulta.html": "formulário de busca, não chega ao parser",
        },
    ),
    ("tjrs", "cjsg"): Leitura(
        ignorar={"erro_solr.json": "erro do Solr, que o parser levanta de propósito"},
    ),
    ("tjsc", "cjsg"): _PAGINAS,
    ("tjto", "cjsg"): Leitura(ignorar={"ementa_*.json": "resposta do cjsg_ementa, outro endpoint"}),
    ("tjto", "cjpg"): _PAGINAS,
    ("trf1", "cpopg"): _PJE_CPOPG,
    ("trf5", "cpopg"): _PJE_CPOPG,
    ("tjpe", "cpopg"): Leitura(
        _detalhe_com_cnj,
        ignorar={
            **_PJE_CPOPG_BUSCA,
            "waf_challenge.html": "desafio do AWS WAF, que o download repete com cookie novo",
        },
    ),
    ("trf6", "cpopg"): Leitura(
        _detalhe_com_cnj,
        ignorar={
            "form_*.html": "formulário de busca ou desafio, não chega ao parser",
            "search_*.html": "resposta da busca, lida no download",
        },
    ),
    ("trf3", "cjsg"): Leitura(
        sufixos=(".html",),
        ignorar={"index_*.html": "página inicial da pesquisa, não chega ao parser"},
    ),
    ("stf", "listar_decisoes"): Leitura(_json_solto, _decisoes_stf, sufixos=(".json",)),
    ("stf", "contar_decisoes"): Leitura(_json_solto, parse_contagem, sufixos=(".json",)),
    ("datajud", "listar_processos"): Leitura(_json_solto, parse_datajud_api_response, sufixos=(".json",)),
    ("comunica_cnj", "listar_comunicacoes"): Leitura(_resposta_comunica_cnj, parse_items, sufixos=(".json",)),
    ("jusbr", "cpopg"): Leitura(
        _detalhes_jusbr,
        _linha_jusbr,
        sufixos=(".json",),
        ignorar={
            "list_*.json": "listagem, lida no download para achar o processo",
            "typical_single.json": "listagem, lida no download para achar o processo",
        },
    ),
    ("falcao", "listar_decisoes"): Leitura(
        _colecao_falcao, parse_documentos, pasta="pesquisa", sufixos=(".json",),
    ),
    ("pdpj", "cpopg"): Leitura(
        _detalhes_jusbr,
        _linhas_pdpj,
        sufixos=(".json",),
        ignorar={"processo_nao_encontrado.json": "lista vazia; a linha de 'Nao encontrado' sai do client"},
    ),
}

# Endpoints sem sample que o parser leia sozinho. Motivo obrigatório.
SEM_LEITURA: dict[tuple[str, str], str] = {
    ("trf3", "cpopg"): (
        "o bruto do parser junta várias respostas JSON por processo (dados, partes, "
        "movimentações, documentos); colunas fixas em trf3/parse.py, conferidas por test_output_parity"
    ),
    ("trf3", "cposg"): (
        "o bruto do parser junta várias respostas JSON por processo; colunas fixas em "
        "trf3/parse.py, conferidas por test_output_parity"
    ),
    ("jusbr", "download_documents"): "devolve texto/binário de documento, sem samples de DataFrame",
    ("pdpj", "download_documents"): "devolve texto/binário de documento, sem samples de DataFrame",
}

# Só a conferência 1 (nomes deprecados). Motivo obrigatório.
SO_NOMES_DEPRECADOS: dict[tuple[str, str], str] = {
    ("tjdft", "cjsg"): "repassa cada registro do JSON da API com 4 chaves renomeadas; extra='allow' é o contrato",
    ("stf", "listar_decisoes"): "repassa o _source da API com 6 chaves renomeadas; extra='allow' é o contrato",
    ("datajud", "listar_processos"): "repassa o _source do Elasticsearch; extra='allow' é o contrato",
    ("comunica_cnj", "listar_comunicacoes"): "repassa os itens do JSON da API; extra='allow' é o contrato",
    ("jusbr", "cpopg"): "repassa os detalhes do PDPJ-CNJ; extra='allow' é o contrato",
    ("falcao", "listar_decisoes"): "garante as colunas canônicas e repassa os campos brutos de cada coleção",
    ("tjsp", "cpopg"): "devolve 4 DataFrames; o Output cobre só o pivot (id_cnj)",
    ("tjsp", "cposg"): "devolve as tabelas do processo em colunas aninhadas; o Output cobre só o pivot",
    ("trf1", "cpopg"): _MOTIVO_PJE_PIVOT,
    ("trf5", "cpopg"): _MOTIVO_PJE_PIVOT,
    ("tjpe", "cpopg"): _MOTIVO_PJE_PIVOT,
    ("trf6", "cpopg"): "o Output cobre só o pivot (id_cnj); o detalhe do eproc vem descrito no docstring",
}

# Colunas entregues e deliberadamente fora do Output, por endpoint. Motivo obrigatório.
_CODIGOS_TJES = "código interno do backend do TJES, ao lado do nome já declarado"
_CODIGOS_TJRS = "código interno do Solr do TJRS, ao lado do nome já declarado (docstring do Output)"
_COLUNAS_CODIGO_TJES = (
    "cd_assunto_principal", "cd_classe_judicial", "id_assunto_principal", "id_bin",
    "id_cargo_julgador", "id_classe_judicial", "id_jurisdicao", "id_localizacao",
)
_COLUNAS_CODIGO_TJRS = (
    "cod_assunto_cnj", "cod_classe_cnj", "cod_ementa", "cod_org_julg", "cod_recurso",
    "cod_redator", "cod_relator", "cod_tipo_documento", "cod_tribunal",
)
AUXILIARES_NAO_DECLARADAS: dict[tuple[str, str], dict[str, str]] = {
    ("tjes", "cjsg"): dict.fromkeys(_COLUNAS_CODIGO_TJES, _CODIGOS_TJES),
    ("tjes", "cjpg"): dict.fromkeys(_COLUNAS_CODIGO_TJES, _CODIGOS_TJES),
    ("tjrs", "cjsg"): {
        "_version_": "versão do documento no Solr; o pydantic não aceita campo com _ inicial",
        **dict.fromkeys(_COLUNAS_CODIGO_TJRS, _CODIGOS_TJRS),
    },
}

# Sinônimo deprecado ainda entregue: o PR que o renomeia ou o motivo de a
# exceção ser permanente. Remover a entrada junto com a correção;
# ``test_excecoes_ainda_sao_necessarias`` cobra isso.
_LISTA_DE_ASSUNTOS = "lista de assuntos do processo, não o assunto único em texto; plural deliberado"
SINONIMOS_TOLERADOS: dict[tuple[str, str, str], str] = {
    # Exceção permanente: ``assuntos`` aqui é a lista de assuntos do processo
    # (código, descrição, principal), não o filtro de busca que o #232 passou
    # ao singular nem o ``assunto`` em texto das outras saídas.
    ("trf6", "cpopg", "assuntos"): _LISTA_DE_ASSUNTOS,
    ("datajud", "listar_processos", "assuntos"): _LISTA_DE_ASSUNTOS,
    ("falcao", "listar_decisoes", "assuntos"): _LISTA_DE_ASSUNTOS,
}


def _pasta(tribunal: str, endpoint: str, leitura: Leitura) -> Path:
    return TESTS / tribunal / "samples" / (leitura.pasta or endpoint)


def _arquivos(tribunal: str, endpoint: str, leitura: Leitura) -> list[Path]:
    return sorted(
        arquivo for arquivo in _pasta(tribunal, endpoint, leitura).iterdir()
        if arquivo.suffix in leitura.sufixos
        and not any(fnmatch.fnmatch(arquivo.name, padrao) for padrao in leitura.ignorar)
    )


def _colunas(resultado: Any) -> set[str]:
    if isinstance(resultado, pd.DataFrame):
        return set(resultado.columns)
    if isinstance(resultado, dict):
        return set().union(*(_colunas(parte) for parte in resultado.values()))
    if isinstance(resultado, list):
        return set().union(*(set(linha) for linha in resultado))
    raise TypeError(f"parser devolveu {type(resultado).__name__}, sem colunas")


@cache
def colunas_entregues(tribunal: str, endpoint: str) -> dict[str, frozenset[str]]:
    """Coluna -> arquivos de sample em que ela aparece."""
    leitura = LEITURAS[(tribunal, endpoint)]
    parser = leitura.parser or getattr(jus.scraper(tribunal), f"{endpoint}_parse")
    onde: dict[str, set[str]] = {}
    for arquivo in _arquivos(tribunal, endpoint, leitura):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                resultado = parser(*leitura.entrada(arquivo))
            except Exception as erro:  # noqa: BLE001 - a mensagem pede ignorar com motivo ou corrigir a leitura
                pytest.fail(
                    f"{tribunal}.{endpoint}: o parser não leu {arquivo.relative_to(TESTS)} "
                    f"({type(erro).__name__}: {erro}). Se o arquivo não é página de resultado "
                    "ou foi escrito à mão, ponha-o em Leitura.ignorar com o motivo."
                )
        for coluna in _colunas(resultado):
            onde.setdefault(coluna, set()).add(arquivo.name)
    return {coluna: frozenset(arquivos) for coluna, arquivos in onde.items()}


CASOS = [pytest.param(tribunal, endpoint, id=f"{tribunal}.{endpoint}") for tribunal, endpoint in LEITURAS]


def _onde(entregues: Mapping[str, frozenset[str]], coluna: str) -> str:
    return ", ".join(sorted(entregues[coluna])[:3])


@pytest.mark.parametrize(("tribunal", "endpoint"), CASOS)
def test_samples_entregam_colunas(tribunal, endpoint):
    """Algum sample lido produz colunas; senão a conferência não confere nada."""
    assert colunas_entregues(tribunal, endpoint), (
        f"{tribunal}.{endpoint}: nenhum sample lido produziu colunas."
    )


@pytest.mark.parametrize(("tribunal", "endpoint"), CASOS)
def test_colunas_entregues_sem_nome_deprecado(tribunal, endpoint):
    entregues = colunas_entregues(tribunal, endpoint)
    proibidas = [
        f"{coluna} (use {DEPRECATED_SYNONYMS[coluna]}; em {_onde(entregues, coluna)})"
        for coluna in sorted(entregues)
        if coluna in DEPRECATED_SYNONYMS and (tribunal, endpoint, coluna) not in SINONIMOS_TOLERADOS
    ]
    assert not proibidas, (
        f"{tribunal}.{endpoint} entrega coluna com nome deprecado:\n * "
        + "\n * ".join(proibidas)
        + "\nRenomeie no parser (breaking change, com entrada no CHANGELOG). "
        "CONTRIBUTING.md > Schemas pydantic > Colunas entregues."
    )


def _nao_declaradas(tribunal: str, endpoint: str) -> list[str]:
    """Colunas entregues fora do Output, de AUXILIARES_NAO_DECLARADAS e de SINONIMOS_TOLERADOS."""
    declaradas = set(resolve(*OUTPUT_SCHEMAS[(tribunal, endpoint)]).model_fields)
    auxiliares = AUXILIARES_NAO_DECLARADAS.get((tribunal, endpoint), {})
    return [
        coluna
        for coluna in sorted(colunas_entregues(tribunal, endpoint))
        if coluna not in declaradas
        and coluna not in auxiliares
        and (tribunal, endpoint, coluna) not in SINONIMOS_TOLERADOS
    ]


@pytest.mark.parametrize(("tribunal", "endpoint"), CASOS)
def test_colunas_entregues_estao_declaradas(tribunal, endpoint):
    if (tribunal, endpoint) in SO_NOMES_DEPRECADOS:
        pytest.skip(SO_NOMES_DEPRECADOS[(tribunal, endpoint)])
    class_name = OUTPUT_SCHEMAS[(tribunal, endpoint)][1]
    entregues = colunas_entregues(tribunal, endpoint)
    fora = [
        f"{coluna} (em {_onde(entregues, coluna)})" for coluna in _nao_declaradas(tribunal, endpoint)
    ]
    assert not fora, (
        f"{tribunal}.{endpoint} entrega colunas que {class_name} não declara:\n * "
        + "\n * ".join(fora)
        + "\nSe o nome é canônico, declare o campo no Output; se é sinônimo de um "
        "nome canônico, renomeie no parser; se é auxiliar do backend, registre em "
        "AUXILIARES_NAO_DECLARADAS com o motivo. CONTRIBUTING.md > Schemas pydantic > "
        "Colunas entregues."
    )


def test_registro_cobre_todos_os_outputs():
    """Todo endpoint com Output tem leitura de samples ou motivo para não ter."""
    lidos, sem = set(LEITURAS), set(SEM_LEITURA)
    assert not lidos & sem, f"Endpoint com leitura e em SEM_LEITURA: {sorted(lidos & sem)}"
    assert lidos | sem == set(OUTPUT_SCHEMAS), (
        f"Sem leitura nem motivo: {sorted(set(OUTPUT_SCHEMAS) - lidos - sem)}; "
        f"fora de EXPECTED_*_OUTPUT_SCHEMAS: {sorted((lidos | sem) - set(OUTPUT_SCHEMAS))}"
    )


def test_excecoes_ainda_sao_necessarias():
    """Exceção que já não faz diferença nos samples é órfã: remover.

    Vale para coluna auxiliar ou sinônimo que sumiu dos samples, endpoint de
    :data:`SO_NOMES_DEPRECADOS` que já declara toda coluna entregue e padrão de
    ``Leitura.ignorar`` que não casa com nenhum arquivo da pasta.
    """
    orfas = [
        f"SO_NOMES_DEPRECADOS: {chave}" for chave in SO_NOMES_DEPRECADOS if chave not in LEITURAS
    ]
    orfas += [
        f"SO_NOMES_DEPRECADOS: {tribunal}.{endpoint} (toda coluna entregue já está declarada)"
        for tribunal, endpoint in SO_NOMES_DEPRECADOS
        if (tribunal, endpoint) in LEITURAS and not _nao_declaradas(tribunal, endpoint)
    ]
    for (tribunal, endpoint), leitura in LEITURAS.items():
        nomes = [arquivo.name for arquivo in _pasta(tribunal, endpoint, leitura).iterdir()]
        orfas += [
            f"Leitura.ignorar: {tribunal}.{endpoint} {padrao!r} (nenhum arquivo da pasta)"
            for padrao in leitura.ignorar
            if not fnmatch.filter(nomes, padrao)
        ]
    for (tribunal, endpoint), colunas in AUXILIARES_NAO_DECLARADAS.items():
        entregues = colunas_entregues(tribunal, endpoint)
        orfas += [
            f"AUXILIARES_NAO_DECLARADAS: {tribunal}.{endpoint}.{coluna}"
            for coluna in colunas if coluna not in entregues
        ]
    for tribunal, endpoint, coluna in SINONIMOS_TOLERADOS:
        if coluna not in colunas_entregues(tribunal, endpoint):
            orfas.append(f"SINONIMOS_TOLERADOS: {tribunal}.{endpoint}.{coluna}")
    assert not orfas, (
        "Exceções que já não fazem diferença nos samples (a correção provavelmente entrou; "
        "remover a entrada):\n * " + "\n * ".join(orfas)
    )
