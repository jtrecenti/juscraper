"""Captura os samples do ``cpopg`` do TRF5 (PJe de 1º grau) no ar.

Rodar da raiz do repositório::

    uv run python -m tests.fixtures.capture.trf5

Grava em ``tests/trf5/samples/cpopg/`` ``form_initial.html``,
``search_one_result.html``, ``detail_normal.html`` e
``search_no_results.html``. O ``movs_page_2.html`` não sai daqui.

Os arquivos saem do ``cpopg_download`` de :class:`TRF5Scraper`, o fluxo de
produção, por um hook de resposta na sessão: se o TRF5 deixar de aceitar o que
o raspador manda, este script quebra antes, em vez de gravar samples velhos.
Os bytes são gravados como vieram, sem decodificar, e só depois de
conferidas todas as respostas.
"""
from __future__ import annotations

import logging

from juscraper.courts._trf.download import DETAIL_PATH, LISTVIEW_PATH
from juscraper.courts.trf5.client import TRF5Scraper

from ._util import dump, respostas_do_cpopg, rotas, samples_dir_for

logger = logging.getLogger(__name__)

# CNJ com um único resultado, de data/amostra_jf_primeiro_grau.csv: CEJUSC
# Maceió (AL).
FOUND_CNJ = "00584573120254058000"

# CNJ com a forma de um processo do TRF5, para passar pela máscara do
# formulário; a busca volta sem token ``ca``.
MISSING_CNJ = "00000000020994050000"


def capturar_consulta() -> dict[str, bytes]:
    """Formulário, buscas e detalhe, pelo ``cpopg_download`` do raspador."""
    scraper = TRF5Scraper(sleep_time=0.5)
    listview = scraper.BASE_URL + LISTVIEW_PATH
    detalhe = scraper.BASE_URL + DETAIL_PATH

    html, respostas = respostas_do_cpopg(scraper, FOUND_CNJ)
    # Sem página extra de movimentações ou documentos: o contrato só registra estas três.
    esperado = [f"GET {listview}", f"POST {listview}", f"GET {detalhe}"]
    obtidas = rotas(respostas)
    if html is None or obtidas != esperado:
        raise RuntimeError(
            f"[trf5] {FOUND_CNJ}: esperava formulário, busca e detalhe numa página só, "
            f"veio {obtidas} (processo arquivado, em segredo ou grande demais?)"
        )
    nomes = ("form_initial.html", "search_one_result.html", "detail_normal.html")
    arquivos = {nome: resp.content for nome, resp in zip(nomes, respostas, strict=True)}

    # Sem token ``ca``, o download para na busca: só um POST.
    _, respostas = respostas_do_cpopg(scraper, MISSING_CNJ)
    obtidas = rotas(respostas)
    if obtidas != [f"POST {listview}"]:
        raise RuntimeError(f"[trf5] {MISSING_CNJ}: esperava uma busca sem resultado, veio {obtidas}")
    arquivos["search_no_results.html"] = respostas[0].content
    return arquivos


def main() -> None:
    """Grava os samples do ``cpopg`` do TRF5, só depois de conferir todas as respostas."""
    dest = samples_dir_for("trf5", "cpopg")
    for nome, conteudo in capturar_consulta().items():
        dump(dest / nome, conteudo)
        logger.info("[trf5] cpopg/%s (%d bytes)", nome, len(conteudo))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
