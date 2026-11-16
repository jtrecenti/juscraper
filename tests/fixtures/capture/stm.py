"""Captura os samples do cjsg do STM.

Da raiz do repositório, de um IP que o WAF do portal aceite (em 16/11/2026
ele recusou um IP de datacenter fora do Brasil e aceitou um IP residencial
brasileiro)::

    python -m tests.fixtures.capture.stm                      # todos os cenários
    python -m tests.fixtures.capture.stm avancada_datas.html  # só os arquivos pedidos

Grava as respostas cruas em ``tests/stm/samples/cjsg/``. ``waf_rejected.html``
não sai daqui: é a página que o WAF devolve a um IP recusado.
"""
import sys
import time
from typing import Any

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL, build_cjsg_params, conferir_bloqueio

from ._util import dump, samples_dir_for

# Cada cenário: arquivo de destino, termo pesquisado, página e os demais
# argumentos de ``build_cjsg_params``.
CENARIOS: list[tuple[str, str, int, dict[str, Any]]] = [
    ("results_normal_page_01.html", '"corrupção ativa"', 1, {}),
    ("results_normal_page_02.html", '"corrupção ativa"', 2, {}),
    ("results_normal_page_03.html", '"corrupção ativa"', 3, {}),
    ("single_page.html", "0000088-44.2014.7.07.0007", 1, {"campo": "numero"}),
    ("no_results.html", "juscraper_probe_zero_hits_xyzqwe", 1, {}),
    # Pesquisa avançada: intervalo de data de julgamento, sem termo.
    (
        "avancada_datas.html",
        "",
        1,
        {
            "datas": {"data_julgamento_inicio": "2010-01-01", "data_julgamento_fim": "2022-06-08"},
            "relator": "CLAUDIO PORTUGAL DE VIVEIROS",
        },
    ),
]


def main() -> None:
    """Captura os samples do cjsg do STM com a sessão do raspador."""
    pedidos = set(sys.argv[1:])
    if desconhecidos := pedidos - {cenario[0] for cenario in CENARIOS}:
        raise SystemExit(f"Cenário desconhecido: {sorted(desconhecidos)}")
    cenarios = [cenario for cenario in CENARIOS if not pedidos or cenario[0] in pedidos]
    dest = samples_dir_for("stm", "cjsg")
    session = jus.scraper("stm").session
    for i, (arquivo, pesquisa, pagina, filtros) in enumerate(cenarios):
        if i:
            time.sleep(3)
        resposta = session.get(BASE_URL, params=build_cjsg_params(pesquisa, pagina, **filtros), timeout=60)
        resposta.raise_for_status()
        conferir_bloqueio(resposta)
        dump(dest / arquivo, resposta.content)


if __name__ == "__main__":
    main()
