"""Capture catalog and full-text (inteiro teor) samples for TSE.

Run from repo root::

    python -m tests.fixtures.capture.tse

The search endpoint is not captured: it requires a captcha token. The
full-text service refuses requests less than ~10 s apart, so the script waits
between them; the ``excesso_requisicoes`` scenario is two requests in a row on
purpose.
"""
import logging
import time

import requests

from juscraper.courts.tse.download import (
    CATALOGO_BODY,
    CATALOGOS,
    INTERVALO_INTEIRO_TEOR,
    catalogo_url,
    inteiro_teor_url,
)

from ._util import dump, samples_dir_for

logger = logging.getLogger("tests.fixtures.capture.tse")

# (cenario, codigoDecisao). Códigos citados em páginas públicas dos TREs.
INTEIRO_TEOR = (
    ("pdf_puro.bin", "2972172"),
    ("envelope_multipart.bin", "3522031"),
    ("codigo_inexistente.txt", "1"),
)


def main() -> None:
    """Capture the four catalogs and the full-text response formats."""
    logging.basicConfig(level=logging.INFO, format="[tse] %(message)s")
    session = requests.Session()
    session.headers.update({"User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)"})

    for catalogo in CATALOGOS:
        response = session.post(catalogo_url(catalogo), json=CATALOGO_BODY, timeout=60)
        response.raise_for_status()
        dump(samples_dir_for("tse", "catalogos") / f"{catalogo}.json", response.content)
        logger.info("wrote catalogos/%s.json (%d bytes)", catalogo, len(response.content))

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
    dump(dest / "excesso_requisicoes.txt", response.content)
    logger.info("wrote inteiro_teor/excesso_requisicoes.txt: %r", response.text[:80])


if __name__ == "__main__":
    main()
