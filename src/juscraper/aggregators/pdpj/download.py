"""Funcoes de download para o agregador PDPJ.

A API ``api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1``
e um conjunto de endpoints REST GET autenticados via JWT
(``Authorization: Bearer <token>``). Cada chamada devolve JSON estruturado
ou, no caso de ``/documentos/{id}/texto``, ``text/plain`` em UTF-8.

Os ``fetch_*`` recebem ``request_fn``, o ``HTTPScraper._request_with_retry``
ligado do :class:`~juscraper.aggregators.pdpj.client.PdpjScraper`, e escolhem
o perfil da chamada (``"listagem"`` ou ``"documento"``); timeout, tentativas e
status retentáveis vêm do perfil, e por isso nenhuma chamada passa
``timeout=``, que venceria o perfil. Nenhum ``fetch_*`` devolve ``None`` por
falha: o erro sobe para o cliente, que decide entre linha de falha e erro.
Resposta 200 cujo corpo não tem a forma esperada levanta
:class:`~juscraper.core.exceptions.InvalidJSONResponseError`.
"""
from __future__ import annotations

import logging
from typing import Any, TypeVar

import requests

from ...core.exceptions import InvalidJSONResponseError
from ...core.http import RequestFn

logger = logging.getLogger(__name__)

_Forma = TypeVar("_Forma", list[Any], dict[str, Any])

# Base URL completa da API DATALAKE - API Processos.
BASE_URL = "https://api-processo-integracao.data-lake.pdpj.jus.br/processo-api/api/v1"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PERFIL_LISTAGEM = "listagem"
PERFIL_DOCUMENTO = "documento"


def _forma_invalida(response: requests.Response) -> InvalidJSONResponseError:
    """Erro para um 200 cujo corpo não tem a forma que o endpoint documenta."""
    return InvalidJSONResponseError(
        response.url,
        response.status_code,
        1,
        response.headers.get("Content-Type"),
        response.text[:200],
    )


def _json(response: requests.Response, forma: type[_Forma]) -> _Forma:
    """Lê o corpo JSON e confere o tipo do topo.

    Corpo que não é JSON e JSON de outro tipo levantam o mesmo
    ``InvalidJSONResponseError``: para quem consome, os dois são "o corpo não é
    o JSON esperado". A leitura não é retentada: um corpo errado num 200 não é
    status transitório, e retentar só atrasaria a mesma falha.
    """
    try:
        data = response.json()
    except ValueError as exc:
        raise _forma_invalida(response) from exc
    if not isinstance(data, forma):
        raise _forma_invalida(response)
    return data


def fetch_processo_existe(
    request_fn: RequestFn,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> bool:
    """Indica se o processo existe na base do Data Lake (endpoint ``/existe``).

    Raises:
        InvalidJSONResponseError: Quando o corpo não é ``true`` nem ``false``.
    """
    url = f"{base_url}/processos/{numero_processo}/existe"
    response = request_fn("GET", url, perfil=PERFIL_LISTAGEM)
    body = response.text.strip().lower()
    if body not in ("true", "false"):
        raise _forma_invalida(response)
    return body == "true"


def fetch_processo_detalhes(
    request_fn: RequestFn,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> list[dict[str, Any]]:
    """Recupera os detalhes do processo. A API responde com **lista** de tramitacoes.

    Lista vazia é o processo que a API não encontrou. Um objeto no lugar da
    lista, ou item da lista que não é objeto, é forma errada, e não um
    processo único: aceitá-lo escondia uma mudança de contrato da API.
    """
    url = f"{base_url}/processos/{numero_processo}"
    response = request_fn("GET", url, perfil=PERFIL_LISTAGEM)
    detalhes: list[dict[str, Any]] = _json(response, list)
    if not all(isinstance(item, dict) for item in detalhes):
        raise _forma_invalida(response)
    return detalhes


def _fetch_objeto(request_fn: RequestFn, url: str) -> dict[str, Any]:
    response = request_fn("GET", url, perfil=PERFIL_LISTAGEM)
    data: dict[str, Any] = _json(response, dict)
    return data


def fetch_processo_documentos(
    request_fn: RequestFn,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Recupera a lista de documentos do processo."""
    return _fetch_objeto(request_fn, f"{base_url}/processos/{numero_processo}/documentos")


def fetch_processo_movimentos(
    request_fn: RequestFn,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Recupera a lista de movimentos do processo."""
    return _fetch_objeto(request_fn, f"{base_url}/processos/{numero_processo}/movimentos")


def fetch_processo_partes(
    request_fn: RequestFn,
    numero_processo: str,
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Recupera a lista de partes do processo."""
    return _fetch_objeto(request_fn, f"{base_url}/processos/{numero_processo}/partes")


def fetch_documento_texto(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> str:
    """Recupera o texto bruto de um documento (UTF-8)."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/texto"
    response = request_fn("GET", url, perfil=PERFIL_DOCUMENTO)
    try:
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "Decodificacao UTF-8 falhou para doc %s do processo %s. Usando response.text.",
            id_documento, numero_processo,
        )
        return response.text


def fetch_documento_binario(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> bytes:
    """Recupera o binario do documento (HTML, PDF, imagem etc)."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/binario"
    response = request_fn("GET", url, perfil=PERFIL_DOCUMENTO)
    return response.content


def fetch_documento_binario_url(
    request_fn: RequestFn,
    numero_processo: str,
    id_documento: str,
    *,
    base_url: str = BASE_URL,
) -> str:
    """Retorna uma URL temporaria com TTL para o binario do documento."""
    url = f"{base_url}/processos/{numero_processo}/documentos/{id_documento}/binario-url"
    response = request_fn("GET", url, perfil=PERFIL_DOCUMENTO)
    return response.text.strip().strip('"')


def fetch_pesquisa(
    request_fn: RequestFn,
    params: dict[str, Any],
    *,
    base_url: str = BASE_URL,
) -> dict[str, Any]:
    """Pesquisa profunda em ``/processos`` (paginacao via ``searchAfter``).

    A página sem registros costuma vir como 404, que sobe como
    ``requests.HTTPError`` e o laço da ``pesquisa`` trata como fim da coleta.
    A forma em 200 abaixo continua aceita, para o caso de a API voltar a usá-la.

    O objeto precisa trazer ``content`` como lista: sem ela, o laço da
    ``pesquisa`` leria uma página vazia e encerraria a coleta em silêncio.
    A exceção é ``content: null`` com ``numberOfElements`` inteiro igual a 0 (não ``false`` nem ``0.0``), que vira
    lista vazia. A API manda ``searchAfter`` preenchido até na última página,
    então toda coleta sem limite pede uma página terminal vazia, e o mesmo
    endpoint serializa outras listas vazias como ``null``. Exigir o zero
    explícito mantém a proteção: uma página com ``null`` que não se declara
    vazia continua sendo forma errada.
    """
    response = request_fn("GET", f"{base_url}/processos", params=params, perfil=PERFIL_LISTAGEM)
    data: dict[str, Any] = _json(response, dict)
    content = data.get("content")
    elementos = data.get("numberOfElements")
    # ``false`` e ``0.0`` também são ``== 0``, e ``bool`` herda de ``int``; a
    # chave ``content`` tem de estar presente, com ``null``.
    zero = isinstance(elementos, int) and not isinstance(elementos, bool) and elementos == 0
    if "content" in data and content is None and zero:
        return {**data, "content": []}
    if not isinstance(content, list):
        raise _forma_invalida(response)
    return data


def _contagem(response: requests.Response) -> int | None:
    """Extrai o total das formas aceitas: ``42``, JSON ``42`` ou ``{"total": 42}``."""
    try:
        return int(response.text.strip())
    except ValueError:
        pass
    try:
        data = response.json()
    except ValueError:
        return None
    # ``bool`` herda de ``int``: ``true`` não é contagem.
    if isinstance(data, int) and not isinstance(data, bool):
        return data
    if isinstance(data, dict):
        for key in ("total", "count", "valor"):
            value = data.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def fetch_contar(
    request_fn: RequestFn,
    params: dict[str, Any],
    *,
    base_url: str = BASE_URL,
) -> int:
    """Total de processos que casam com ``params`` (``/processos:contar``).

    Raises:
        InvalidJSONResponseError: Quando o corpo não traz um inteiro.
    """
    response = request_fn("GET", f"{base_url}/processos:contar", params=params, perfil=PERFIL_LISTAGEM)
    total = _contagem(response)
    if total is None:
        raise _forma_invalida(response)
    return total
