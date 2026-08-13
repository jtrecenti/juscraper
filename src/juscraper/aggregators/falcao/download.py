"""Funcoes de download para o agregador Falcao (Jurisprudencia Nacional da JT).

O endpoint publico e um GET REST com paginacao ``page``/``size`` (0-based na
querystring). Cada chamada devolve um JSON com:

- ``documentos`` (list[dict]): a pagina atual da colecao consultada.
- ``quantidadeTotal`` (int): total de documentos que casam com o filtro
  (limitado a 10000 pelo backend Elasticsearch).
- ``temasTopFive`` (list[dict]): temas/precedentes destacados (ignorado).

Guardas do backend descobertas por engenharia reversa (ver ``schemas.py``):

- ``sessionId`` e **obrigatorio** — sem ele o backend responde 403
  ``"Tentativa invalida de acesso ao sistema"``. O frontend gera um id
  aleatorio (``"_" + 7 chars base36``) e o guarda num cookie; replicamos.
- ``Origin``/``Referer`` do site oficial sao checados pelo WAF (403 sem eles).
"""
from __future__ import annotations

import logging
import secrets
import string
from typing import Any

logger = logging.getLogger(__name__)

BASE_URL = "https://jurisprudencia.jt.jus.br/jurisprudencia-nacional-backend/api"
SEARCH_URL = f"{BASE_URL}/no-auth/pesquisa"

_SITE_ORIGIN = "https://jurisprudencia.jt.jus.br"

DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,en-US;q=0.7,en;q=0.3",
    "Origin": _SITE_ORIGIN,
    "Referer": f"{_SITE_ORIGIN}/jurisprudencia-nacional/home",
    # O WAF (CloudFront) do site responde 403 a User-Agents nao-navegador —
    # inclusive o UA padrao do juscraper. Sobrescrevemos com um UA de
    # navegador, como faz o agregador ComunicaCNJ.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:139.0) "
        "Gecko/20100101 Firefox/139.0"
    ),
}

# Mapeamento nome-canonico (juscraper) -> parametro do backend. Cada valor e
# uma lista no schema; a querystring espera CSV.
_FILTROS_CSV: dict[str, str] = {
    "tribunais": "tribunais",
    "relator": "nomeRelator",
    "orgao_julgador": "orgaoJulgador",
    "classe": "classeProcesso",
    "fase_processual": "faseProcessual",
    "prioridade": "prioridade",
}


def gerar_session_id() -> str:
    """Gera um ``sessionId`` no formato que o frontend usa (``_`` + 7 base36).

    O backend so exige que o parametro exista e tenha esse formato; nao ha
    registro previo. Gerado uma vez por instancia de scraper e reusado em
    todas as paginas (espelha o cookie de 30 dias do frontend).
    """
    alfabeto = string.ascii_lowercase + string.digits
    return "_" + "".join(secrets.choice(alfabeto) for _ in range(7))


def _as_csv(valor: str | list[str]) -> str:
    """Serializa um filtro (str ou list[str]) para o CSV que o backend espera."""
    if isinstance(valor, (list, tuple)):
        return ",".join(str(v) for v in valor)
    return str(valor)


def build_pesquisa_params(
    *,
    pesquisa: str,
    colecao: str,
    session_id: str,
    pagina: int,
    tamanho_pagina: int = 10,
    tribunais: str | list[str] | None = None,
    relator: str | list[str] | None = None,
    orgao_julgador: str | list[str] | None = None,
    classe: str | list[str] | None = None,
    fase_processual: str | list[str] | None = None,
    prioridade: str | list[str] | None = None,
    tem_ementa: bool | None = None,
    somente_ementa: bool | None = None,
    ordenacao: str | None = None,
    data_juntada_inicio: str | None = None,
    data_juntada_fim: str | None = None,
) -> dict[str, Any]:
    """Monta a querystring aceita pelo endpoint ``/no-auth/pesquisa``.

    Args:
        pesquisa: Termo livre (parametro ``texto``).
        colecao: Colecao alvo (obrigatoria no backend).
        session_id: Id de sessao (:func:`gerar_session_id`).
        pagina: Numero da pagina **1-based** da API publica do juscraper —
            convertido aqui para o ``page`` 0-based do backend.
        tamanho_pagina: ``size`` (5 ou 10 para nao autenticado).
        tribunais..prioridade: Filtros multivalorados (str ou list[str]);
            serializados como CSV.
        tem_ementa / somente_ementa: Flags booleanas (``temEmenta`` /
            ``pesquisaSomenteNasEmentas``).
        ordenacao: ``ordenacao`` (``mais_relevante``/``mais_recente``/
            ``menos_recente``).
        data_juntada_inicio / data_juntada_fim: Intervalo de ``dataJuntada``
            em ISO ``AAAA-MM-DD`` (``dataInicio`` / ``dataFim`` no backend).
    """
    params: dict[str, Any] = {
        "texto": pesquisa,
        "colecao": colecao,
        "sessionId": session_id,
        "page": max(0, pagina - 1),
        "size": tamanho_pagina,
    }

    filtros_locais = {
        "tribunais": tribunais,
        "relator": relator,
        "orgao_julgador": orgao_julgador,
        "classe": classe,
        "fase_processual": fase_processual,
        "prioridade": prioridade,
    }
    for nome, valor in filtros_locais.items():
        if valor is not None and valor != []:
            params[_FILTROS_CSV[nome]] = _as_csv(valor)

    if tem_ementa is not None:
        params["temEmenta"] = str(tem_ementa).lower()
    if somente_ementa is not None:
        params["pesquisaSomenteNasEmentas"] = str(somente_ementa).lower()
    if ordenacao is not None:
        params["ordenacao"] = ordenacao
    if data_juntada_inicio is not None:
        params["dataInicio"] = data_juntada_inicio
    if data_juntada_fim is not None:
        params["dataFim"] = data_juntada_fim

    return params
