"""Capture listar_decisoes/contar_decisoes samples for STF.

Run from repo root::

    python -m tests.fixtures.capture.stf

Precisa do extra ``stf`` (Playwright) para obter o cookie ``aws-waf-token``.
Os samples sao saneados para caber no repositorio: ``decisao_texto``,
``ementa_texto`` e ``partes_lista_texto`` truncados em 300 caracteres e o bloco
``highlight`` de cada hit removido.
"""
import json

from juscraper.courts.stf.client import STFScraper
from juscraper.courts.stf.download import build_payload

from ._util import dump, samples_dir_for

_CAMPOS_LONGOS = ("decisao_texto", "ementa_texto", "partes_lista_texto")


def _sanear(resposta: dict) -> dict:
    for hit in resposta["result"]["hits"]["hits"]:
        hit.pop("highlight", None)
        for campo in _CAMPOS_LONGOS:
            valor = hit["_source"].get(campo)
            if isinstance(valor, str):
                hit["_source"][campo] = valor[:300]
    return resposta


def _capture(stf: STFScraper, endpoint: str, filename: str, **payload_kwargs) -> None:
    resposta = _sanear(stf._buscar(build_payload(**payload_kwargs)))  # pylint: disable=protected-access
    dest = samples_dir_for("stf", endpoint)
    dump(dest / filename, json.dumps(resposta, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"[stf] wrote {endpoint}/{filename}")


def main() -> None:
    """Capture JSON samples for STF."""
    stf = STFScraper()
    _capture(stf, "listar_decisoes", "results_normal_page_01.json",
             pesquisa="pejotização", classe="Rcl", pagina=1, tamanho_pagina=5)
    _capture(stf, "listar_decisoes", "results_normal_page_02.json",
             pesquisa="pejotização", classe="Rcl", pagina=2, tamanho_pagina=5)
    _capture(stf, "listar_decisoes", "single_page.json",
             pesquisa="pejotização", pagina=1, tamanho_pagina=250,
             data_julgamento_inicio="01012020", data_julgamento_fim="31122020")
    _capture(stf, "listar_decisoes", "no_results.json",
             pesquisa="juscraper_probe_zero_hits_xyzqwe", pagina=1, tamanho_pagina=250)
    _capture(stf, "contar_decisoes", "results_normal.json",
             pesquisa="pejotização", classe="Rcl", tamanho_pagina=0)


if __name__ == "__main__":
    main()
