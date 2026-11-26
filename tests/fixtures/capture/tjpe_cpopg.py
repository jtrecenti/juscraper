"""Captura o desafio do AWS WAF na consulta pública do PJe de 1º grau do TJPE.

Rodar da raiz do repositório::

    python -m tests.fixtures.capture.tjpe_cpopg

Grava ``tests/tjpe/samples/cpopg/waf_challenge.html``: a página de JavaScript
que o WAF serve, com HTTP 202, no lugar do formulário da consulta. Com o
User-Agent de navegador do raspador o desafio é intermitente; com um cliente
de linha de comando que pede HTML (``curl`` + ``Accept: text/html``) ele vem
sempre (conferido em 26/11/2026). As chaves ``key``, ``iv`` e ``context`` mudam
a cada resposta e não identificam ninguém.

O ``form_initial.html`` da mesma pasta não é gravado aqui.
"""
from __future__ import annotations

import logging

import requests

from juscraper.core.waf import eh_desafio_waf
from juscraper.courts._trf.download import LISTVIEW_PATH
from juscraper.courts.tjpe.consulta_publica import TJPEConsultaPublicaScraper

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

# Cliente sem cara de navegador que pede HTML: o WAF desafia toda vez. Só estes
# dois cabeçalhos; com os padrões do ``requests`` (``Accept-Encoding``,
# ``Connection``) o WAF deixa passar.
HEADERS = {"User-Agent": "curl/8.7.1", "Accept": "text/html"}


def main() -> None:
    """Grava a página de desafio do WAF do TJPE."""
    url = TJPEConsultaPublicaScraper.BASE_URL + LISTVIEW_PATH
    session = requests.Session()
    session.headers.clear()
    session.headers.update(HEADERS)
    resp = session.get(url, timeout=30)
    if not eh_desafio_waf(resp) or resp.status_code != 202:
        raise RuntimeError(
            f"[tjpe] esperava o desafio do WAF (HTTP 202) em {url}, veio HTTP {resp.status_code}"
        )
    dest = samples_dir_for("tjpe", "cpopg") / "waf_challenge.html"
    dump(dest, resp.content)
    logger.info("[tjpe] cpopg/waf_challenge.html (%d bytes)", len(resp.content))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
