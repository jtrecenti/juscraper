"""Capture catalog and full-text (inteiro teor) samples for TSE.

Run from repo root::

    python -m tests.fixtures.capture.tse

``python -m tests.fixtures.capture.tse catalogos`` captures only the catalogs.
The search endpoint is not captured: it requires a captcha token. The
full-text service refuses requests less than ~10 s apart, so the script waits
between them; the ``excesso_requisicoes`` scenario is two requests in a row on
purpose.
"""
import logging
import sys
import time

import requests

import juscraper as jus
from juscraper.courts.tse.download import (
    CATALOGO_BODY,
    CATALOGOS,
    EXCESSO_DE_REQUISICOES,
    INTERVALO_INTEIRO_TEOR,
    catalogo_url,
    inteiro_teor_url,
)

from ._util import dump, samples_dir_for

logger = logging.getLogger("tests.fixtures.capture.tse")

# Um TRE, o de catálogos menores, para o contrato de ``tribunal=``. O catálogo
# de normas é o mesmo arquivo em todos os tribunais e não é regravado.
TRE = "tre-ac"
CATALOGOS_TRE = ("classes", "relatorias", "eleicoes")

# (cenario, codigoDecisao). Códigos citados em páginas públicas dos TREs.
INTEIRO_TEOR = (
    ("pdf_puro.bin", "2972172"),
    ("envelope_multipart.bin", "3522031"),
    ("codigo_inexistente.txt", "1"),
)


def capturar_catalogos(session: requests.Session) -> None:
    """Capture the catalogs of the TSE and of one TRE."""
    for tribunal, pasta, catalogos in (("tse", "catalogos", CATALOGOS), (TRE, f"catalogos_{TRE}", CATALOGOS_TRE)):
        for catalogo in catalogos:
            response = session.post(catalogo_url(catalogo, tribunal), json=CATALOGO_BODY, timeout=60)
            response.raise_for_status()
            dump(samples_dir_for("tse", pasta) / f"{catalogo}.json", response.content)
            logger.info("wrote %s/%s.json (%d bytes)", pasta, catalogo, len(response.content))


def capturar_inteiro_teor(session: requests.Session) -> None:
    """Capture the full-text response formats."""
    dest = samples_dir_for("tse", "inteiro_teor")
    for filename, codigo in INTEIRO_TEOR:
        response = session.get(inteiro_teor_url(codigo), timeout=120)
        response.raise_for_status()
        dump(dest / filename, response.content)
        logger.info("wrote inteiro_teor/%s (%s)", filename, response.headers.get("Content-Type"))
        time.sleep(INTERVALO_INTEIRO_TEOR + 2)

    # Dois pedidos seguidos: o segundo volta "Excesso de requisições".
    session.get(inteiro_teor_url(INTEIRO_TEOR[0][1]), timeout=120)
    response = session.get(inteiro_teor_url(INTEIRO_TEOR[1][1]), timeout=120)
    inicio = response.content[:300].decode("utf-8", "replace")
    if EXCESSO_DE_REQUISICOES not in inicio:
        raise SystemExit("[tse] o segundo pedido seguido não foi recusado; excesso_requisicoes.txt não foi regravado.")
    dump(dest / "excesso_requisicoes.txt", response.content)
    logger.info("wrote inteiro_teor/excesso_requisicoes.txt: %r", inicio[:80])


def main() -> None:
    """Capture the catalogs and, unless ``catalogos`` is given, the full-text formats."""
    logging.basicConfig(level=logging.INFO, format="[tse] %(message)s")
    # A sessão do raspador, para capturar com os cabeçalhos que ele manda.
    session = jus.scraper("tse").session
    if sys.argv[1:] not in ([], ["catalogos"]):
        raise SystemExit("uso: python -m tests.fixtures.capture.tse [catalogos]")
    capturar_catalogos(session)
    if not sys.argv[1:]:
        capturar_inteiro_teor(session)


if __name__ == "__main__":
    main()
