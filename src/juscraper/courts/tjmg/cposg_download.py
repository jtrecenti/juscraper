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

import requests

from juscraper.core.http import RequestFn

logger = logging.getLogger("juscraper.tjmg")

BASE = "https://www4.tjmg.jus.br/juridico/sf"
RESULTADO_URL = f"{BASE}/proc_resultado2.jsp"
PARTES_URL = f"{BASE}/proc_partes_advogados2.jsp"

# O backend serve ISO-8859-1 sem declarar charset de forma confiavel.
ENCODING = "iso-8859-1"


def _get(request_fn: RequestFn, url: str, numero: str) -> str:
    resp = request_fn("GET", url, params={"listaProcessos": numero}, timeout=60)
    return resp.content.decode(ENCODING)


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
    for i, numero in enumerate(numeros):
        if i and sleep_time:
            time.sleep(sleep_time)
        item: dict = {"id_cnj": numero, "resultado": None, "partes": {}}
        try:
            resultado = fetch_resultado(request_fn, numero)
        except requests.RequestException as exc:
            logger.warning("TJMG cposg: falha ao consultar %s: %s", numero, exc)
            out.append(item)
            continue
        item["resultado"] = resultado
        for numero_tjmg in extract_partes_ids(resultado):
            if sleep_time:
                time.sleep(sleep_time)
            item["partes"][numero_tjmg] = fetch_partes(request_fn, numero_tjmg)
        out.append(item)
    return out
