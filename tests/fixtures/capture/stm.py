"""Captura os samples do cjsg e do listar_processos do STM.

Da raiz do repositório, de um IP que o WAF do portal aceite (em 16/11/2026
ele recusou um IP de datacenter fora do Brasil e aceitou um IP residencial
brasileiro)::

    python -m tests.fixtures.capture.stm                      # todos os cenários
    python -m tests.fixtures.capture.stm avancada_datas.html  # só os arquivos pedidos

Grava as respostas cruas em ``tests/stm/samples/cjsg/`` e, as da aba de
processos, em ``tests/stm/samples/processos/``. ``waf_rejected.html`` não sai
daqui: é a página que o WAF devolve a um IP recusado.
"""
import sys
import time
from typing import Any

import juscraper as jus
from juscraper.courts.stm.download import BASE_URL, build_cjsg_params, build_processos_params, conferir_bloqueio

from ._util import dump, samples_dir_for

# Cada cenário: arquivo de destino, termo pesquisado, página e os demais
# argumentos de ``build_cjsg_params``.
CENARIOS: list[tuple[str, str, int, dict[str, Any]]] = [
    ("results_normal_page_01.html", '"corrupção ativa"', 1, {}),
    ("results_normal_page_02.html", '"corrupção ativa"', 2, {}),
    ("results_normal_page_03.html", '"corrupção ativa"', 3, {}),
    ("single_page.html", "0000088-44.2014.7.07.0007", 1, {"campo": "numero"}),
    ("no_results.html", "juscraper_probe_zero_hits_xyzqwe", 1, {}),
    # As outras duas opções de ``campo`` da busca simples, com um relator para a página sair pequena.
    ("campo_tudo.html", '"corrupção ativa"', 1, {"campo": "tudo", "relator": "CARLOS VUYK DE AQUINO"}),
    (
        "campo_referencia_legislativa.html",
        "290",
        1,
        {"campo": "referencia_legislativa", "relator": "CARLOS VUYK DE AQUINO"},
    ),
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

# Aba de processos: arquivo de destino, número pesquisado e os filtros de
# ``build_processos_params``.
CENARIOS_DE_PROCESSOS: list[tuple[str, str, dict[str, Any]]] = [
    ("por_numero.html", "7000374-06.2020.7.00.0000", {}),
    ("filtro_situacao.html", "", {"assunto": "INCITAMENTO", "situacao": "MOVIMENTO"}),
    ("processos_fisicos.html", "0000028-58.2008.7.01.0101", {}),
]


def main() -> None:
    """Captura os samples do STM com a sessão do raspador."""
    capturas = [
        (samples_dir_for("stm", "cjsg") / arquivo, build_cjsg_params(pesquisa, pagina, **filtros))
        for arquivo, pesquisa, pagina, filtros in CENARIOS
    ] + [
        (samples_dir_for("stm", "processos") / arquivo, build_processos_params(pesquisa, **filtros))
        for arquivo, pesquisa, filtros in CENARIOS_DE_PROCESSOS
    ]
    pedidos = set(sys.argv[1:])
    if desconhecidos := pedidos - {destino.name for destino, _ in capturas}:
        raise SystemExit(f"Cenário desconhecido: {sorted(desconhecidos)}")
    session = jus.scraper("stm").session
    for i, (destino, params) in enumerate(captura for captura in capturas if not pedidos or captura[0].name in pedidos):
        if i:
            time.sleep(3)
        resposta = session.get(BASE_URL, params=params, timeout=60)
        resposta.raise_for_status()
        conferir_bloqueio(resposta)
        dump(destino, resposta.content)


if __name__ == "__main__":
    main()
