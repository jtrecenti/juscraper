"""Montagem do corpo de busca da API de jurisprudencia do STF.

O corpo parte do que o proprio portal envia (``payloads/<base>.json``, capturado
de ``jurisprudencia.stf.jus.br/pages/search`` sem o bloco ``highlight``). Manter o
corpo do portal, e nao uma query minima, faz a busca devolver o mesmo conjunto e a
mesma ordem por relevancia que o site: campos pesquisados, pesos, fuzziness e
decaimento por data vem de la. ``build_payload`` so altera o que os filtros pedem e
acrescenta ``id`` como desempate da ordenacao, de modo que, entre documentos com o
mesmo score, a ordem e por ``id`` e nao a do portal.
"""
from __future__ import annotations

import copy
import json
import re
from functools import cache
from pathlib import Path

BASE_URL = "https://jurisprudencia.stf.jus.br/api/search/search"

MAX_TAMANHO_PAGINA = 250
"""Acima disso a API responde 403 "Excedido o limite de 250 documentos por consulta"."""

MAX_REGISTROS = 10_000
"""Maior ``from + size`` aceito pela API.

Acima disso ela responde 403 "O maior registro que pode ser acessado em uma busca
e o de numero 10000"; buscas maiores precisam ser divididas por intervalo de datas.
"""

BASES = ("decisoes", "acordaos")

_CAMPO_CLASSE = "processo_classe_processual_unificada_classe_sigla.keyword"
_AGG_CLASSE = "processo_classe_processual_unificada_classe_sigla_agg"
_PAYLOADS_DIR = Path(__file__).parent / "payloads"


@cache
def _template(base: str) -> dict:
    template: dict = json.loads((_PAYLOADS_DIR / f"{base}.json").read_text(encoding="utf-8"))
    return template


_OPERADORES = {"e": "AND", "ou": "OR", "não": "NOT", "nao": "NOT"}
_OPERADOR_RE = re.compile(r"(?<!\S)(e|ou|não|nao)(?!\S)", flags=re.IGNORECASE)


def traduzir_operadores(pesquisa: str) -> str:
    """Converte os operadores do portal para a sintaxe ``query_string`` do Elasticsearch.

    Reproduz a traducao que o portal faz antes de enviar: ``e``, ``ou`` e ``não`` como
    palavras soltas viram ``AND``, ``OR`` e ``NOT``, e ``$`` vira o curinga ``*``
    (``terceiriz$`` -> ``terceiriz*``). Trechos entre aspas passam intactos, porque no
    portal os termos entre aspas perdem a funcao de operador. ``?``, ``~`` e parenteses
    ja sao sintaxe do Elasticsearch e passam como estao.
    """
    # Com o grupo de captura, re.split devolve os trechos entre aspas nas posicoes impares.
    trechos = re.split(r'("[^"]*")', pesquisa)
    for i in range(0, len(trechos), 2):
        trechos[i] = _OPERADOR_RE.sub(lambda m: _OPERADORES[m.group(1).lower()], trechos[i].replace("$", "*"))
    return "".join(trechos)


def build_payload(
    pesquisa: str | None = None,
    *,
    pagina: int = 1,
    tamanho_pagina: int = 10,
    base: str = "decisoes",
    classe: str | list[str] | None = None,
    inteiro_teor: bool = False,
    data_julgamento_inicio: str | None = None,
    data_julgamento_fim: str | None = None,
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
) -> dict:
    """Monta o corpo JSON enviado a ``BASE_URL``.

    Compartilhado entre o scraper e o script de captura de samples.

    Args:
        pesquisa (str | None): Termos de busca na sintaxe do portal. ``None`` busca tudo.
        pagina (int): Pagina 1-based.
        tamanho_pagina (int): Documentos por pagina. ``0`` pede so total e agregacoes.
        base (str): ``"decisoes"`` (monocraticas) ou ``"acordaos"``.
        classe (str | list[str] | None): Sigla(s) da classe processual (ex.: ``"Rcl"``).
        inteiro_teor (bool): Pesquisa tambem no inteiro teor, como a opcao do portal.
        data_julgamento_inicio, data_julgamento_fim, data_publicacao_inicio,
        data_publicacao_fim (str | None): Datas ja no formato ``ddMMyyyy``.

    Raises:
        ValueError: Quando a pagina pedida comeca depois do registro 10.000.
    """
    inicio = (pagina - 1) * tamanho_pagina
    if inicio >= MAX_REGISTROS:
        raise ValueError(
            f"A API do STF so entrega os {MAX_REGISTROS} primeiros registros de uma busca, "
            f"e a pagina {pagina} com {tamanho_pagina} por pagina comeca no registro {inicio + 1}. "
            "Divida a busca por intervalo de datas."
        )

    body = copy.deepcopy(_template(base))
    # O score empata com frequencia (sem pesquisa, todas as decisoes julgadas no mesmo dia
    # tem o mesmo score), e cada pagina e uma requisicao separada: sem desempate, o
    # Elasticsearch nao garante a mesma ordem entre paginas e pode repetir ou pular
    # documentos. ``id`` e keyword ordenavel nas duas bases; ``_id`` a API recusa com 400.
    body["sort"].append({"id": "asc"})
    consulta_bool = body["query"]["function_score"]["query"]["bool"]
    busca = consulta_bool["filter"][0]["query_string"]
    reforcos = [clausula["query_string"] for clausula in consulta_bool["should"]]

    consulta = traduzir_operadores(pesquisa) if pesquisa else "*"
    for clausula in [busca, *reforcos]:
        clausula["query"] = consulta

    if inteiro_teor:
        # Mesmos campos e pesos que o portal acrescenta com "pesquisar no inteiro teor".
        busca["fields"].append("inteiro_teor_texto.plural")
        reforcos[0]["fields"].append("inteiro_teor_texto.plural")
        reforcos[1]["fields"].append("inteiro_teor_texto.plural^0.5")

    for campo, data_inicio, data_fim in (
        ("julgamento_data", data_julgamento_inicio, data_julgamento_fim),
        ("publicacao_data", data_publicacao_inicio, data_publicacao_fim),
    ):
        if data_inicio or data_fim:
            faixa: dict[str, str] = {"format": "ddMMyyyy"}
            if data_inicio:
                faixa["from"] = data_inicio
            if data_fim:
                faixa["lte"] = data_fim
            consulta_bool["filter"].append({"range": {campo: faixa}})

    if classe:
        filtro_classe = {"terms": {_CAMPO_CLASSE: [classe] if isinstance(classe, str) else list(classe)}}
        body["post_filter"]["bool"]["must"].append(filtro_classe)
        # A faceta de classe ignora o próprio filtro; todas as outras o respeitam.
        for nome, agg in body["aggs"].items():
            if nome == _AGG_CLASSE:
                continue
            if "filter" in agg:
                agg["filter"]["bool"]["must"].append(filtro_classe)
            else:
                body["aggs"][nome] = {
                    "filter": {"bool": {"must": [filtro_classe]}},
                    "aggs": {nome: agg},
                }

    body["from"] = inicio
    body["size"] = min(tamanho_pagina, MAX_REGISTROS - inicio)
    return body
