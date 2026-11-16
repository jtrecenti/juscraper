"""Captura os samples do cjsg do STM.

Da raiz do repositório, de um IP que o WAF do portal aceite (em 16/11/2026
ele recusou um IP de datacenter fora do Brasil e aceitou um IP residencial
brasileiro)::

    python -m tests.fixtures.capture.stm

Grava as respostas cruas em ``tests/stm/samples/cjsg/``. ``waf_rejected.html``
não sai daqui: é a página que o WAF devolve a um IP recusado.
"""
import time

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL, build_cjsg_params, conferir_bloqueio

from ._util import dump, samples_dir_for

# Cada cenário: arquivo de destino, termo pesquisado, página e filtros.
CENARIOS: list[tuple[str, str, int, dict[str, str]]] = [
    ("results_normal_page_01.html", '"corrupção ativa"', 1, {}),
    ("results_normal_page_02.html", '"corrupção ativa"', 2, {}),
    ("results_normal_page_03.html", '"corrupção ativa"', 3, {}),
    ("single_page.html", "0000088-44.2014.7.07.0007", 1, {"campo": "numero"}),
    ("no_results.html", "juscraper_probe_zero_hits_xyzqwe", 1, {}),
]


def main() -> None:
    """Captura os samples do cjsg do STM com a sessão do raspador."""
    dest = samples_dir_for("stm", "cjsg")
    session = jus.scraper("stm").session
    for i, (arquivo, pesquisa, pagina, filtros) in enumerate(CENARIOS):
        if i:
            time.sleep(3)
        resposta = session.get(BASE_URL, params=build_cjsg_params(pesquisa, pagina, **filtros), timeout=60)
        resposta.raise_for_status()
        conferir_bloqueio(resposta)
        dump(dest / arquivo, resposta.content)


if __name__ == "__main__":
    main()
