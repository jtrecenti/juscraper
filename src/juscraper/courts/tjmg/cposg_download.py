"""HTTP-level helpers for the TJMG second-degree case lookup (``cposg``).

A consulta processual de 2a instancia (``www4.tjmg.jus.br/juridico/sf``)
nao tem captcha. O fluxo usa duas paginas:

1. ``proc_resultado2.jsp?listaProcessos=<numero>`` — aceita CNJ (20 digitos)
   ou numero TJMG (17 digitos) e lista todos os recursos daquele numero
   (dados resumidos + flag de segredo de justica).
2. ``proc_partes_advogados2.jsp?listaProcessos=<numero TJMG>`` — partes e
   advogados (com OAB) de um recurso. So aceita o numero TJMG; com CNJ o
   backend responde HTTP 500.
"""
from __future__ import annotations

import logging
import time
import warnings

import requests
from tqdm.auto import tqdm

from juscraper.core.http import RequestFn

logger = logging.getLogger("juscraper.tjmg")

BASE = "https://www4.tjmg.jus.br/juridico/sf"
RESULTADO_URL = f"{BASE}/proc_resultado2.jsp"
PARTES_URL = f"{BASE}/proc_partes_advogados2.jsp"

# O backend serve ISO-8859-1 sem declarar charset de forma confiavel.
ENCODING = "iso-8859-1"


TIMEOUT = 30
TRANSPORT_ATTEMPTS = 3


def _get(request_fn: RequestFn, url: str, numero: str) -> str:
    """GET com retry para timeout/conexao, que o ``request_fn`` nao cobre.

    O ``request_fn`` ja repete HTTP 5xx; aqui cobrimos o caso observado em
    que o backend responde 500 e, na nova tentativa, trava ate o timeout.
    """
    for attempt in range(1, TRANSPORT_ATTEMPTS + 1):
        try:
            resp = request_fn("GET", url, params={"listaProcessos": numero}, timeout=TIMEOUT)
            return resp.content.decode(ENCODING)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == TRANSPORT_ATTEMPTS:
                raise
            wait = 2.0 ** attempt
            logger.warning(
                "TJMG cposg: %s em %s (tentativa %d/%d). Aguardando %.0fs.",
                type(exc).__name__, numero, attempt, TRANSPORT_ATTEMPTS, wait,
            )
            time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def fetch_resultado(request_fn: RequestFn, numero: str) -> str:
    """Baixa a pagina de resultado (lista de recursos) de um CNJ ou numero TJMG."""
    return _get(request_fn, RESULTADO_URL, numero)


def fetch_partes(request_fn: RequestFn, numero_tjmg: str) -> str | None:
    """Baixa a pagina de partes/advogados de um recurso (numero TJMG, 17 digitos).

    Retorna ``None`` quando o backend falha (HTTP 5xx apos os retries).
    """
    try:
        return _get(request_fn, PARTES_URL, numero_tjmg)
    except requests.RequestException as exc:
        logger.warning("TJMG cposg: falha ao baixar partes de %s: %s", numero_tjmg, exc)
        return None


def cposg_download(
    numeros: list[str],
    request_fn: RequestFn,
    extract_partes_ids,
    sleep_time: float = 1.0,
) -> list[dict]:
    """Baixa resultado + partes de cada numero.

    ``extract_partes_ids`` recebe o HTML do resultado e devolve os numeros
    TJMG (17 digitos) com link de partes — injetado para manter o parsing
    em ``cposg_parse``.

    Retorna uma lista alinhada com ``numeros``; cada item e
    ``{"id_cnj": numero, "resultado": html | None, "partes": {numero_tjmg: html | None}}``.
    """
    out: list[dict] = []
    falhas: list[str] = []
    for i, numero in enumerate(tqdm(numeros, desc="TJMG cposg")):
        if i and sleep_time:
            time.sleep(sleep_time)
        item: dict = {"id_cnj": numero, "resultado": None, "partes": {}}
        try:
            resultado = fetch_resultado(request_fn, numero)
        except requests.RequestException as exc:
            logger.warning("TJMG cposg: falha ao consultar %s: %s", numero, exc)
            falhas.append(numero)
            out.append(item)
            continue
        item["resultado"] = resultado
        for numero_tjmg in extract_partes_ids(resultado):
            if sleep_time:
                time.sleep(sleep_time)
            item["partes"][numero_tjmg] = fetch_partes(request_fn, numero_tjmg)
            if item["partes"][numero_tjmg] is None:
                falhas.append(numero_tjmg)
        out.append(item)
    if falhas:
        warnings.warn(
            f"TJMG cposg: {len(falhas)} consulta(s) falharam apos as retentativas "
            f"e ficaram sem dados: {falhas}. Rode o cposg de novo para esses numeros.",
            UserWarning,
            stacklevel=3,
        )
    return out
