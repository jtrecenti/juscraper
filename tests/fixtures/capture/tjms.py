"""Capture cjsg and cjpg samples for TJMS.

Run from repo root, from a residential IP (``esaj.tjms.jus.br`` does not
answer datacenter IPs)::

    python -m tests.fixtures.capture.tjms
"""
import json
import time

from bs4 import BeautifulSoup

from ._util import build_session, capture_cjsg_samples, dump, make_tjsp_cjpg_params, samples_dir_for

ESAJ_BASE = "https://esaj.tjms.jus.br/"


def capture_cjpg() -> None:
    """Capture cjpg samples and the pasta behind the first sentence.

    Saves under ``tests/tjms/samples/cjpg/``: two pages of ``dano moral``,
    a search with no hits, and, for the first result of page 1, the
    ``Location`` of ``cjpg/obterArquivo.do`` (``redirecionamentos.json``)
    and the pasta digital page it leads to. The PDF itself is not saved:
    the tests only need a body starting with ``%PDF``.
    """
    dest = samples_dir_for("tjms", "cjpg")

    session = build_session()
    session.get(f"{ESAJ_BASE}cjpg/open.do", timeout=60)
    r1 = session.get(f"{ESAJ_BASE}cjpg/pesquisar.do", params=make_tjsp_cjpg_params("dano moral"), timeout=60)
    r1.raise_for_status()
    dump(dest / "results_normal_page_01.html", r1.content)
    time.sleep(1.5)
    r2 = session.get(f"{ESAJ_BASE}cjpg/trocarDePagina.do", params={"pagina": "2", "conversationId": ""}, timeout=60)
    r2.raise_for_status()
    dump(dest / "results_normal_page_02.html", r2.content)

    time.sleep(1.5)
    session = build_session()
    r_none = session.get(
        f"{ESAJ_BASE}cjpg/pesquisar.do",
        params=make_tjsp_cjpg_params("juscraper_probe_zero_hits_xyzqwe"),
        timeout=60,
    )
    r_none.raise_for_status()
    dump(dest / "no_results.html", r_none.content)

    link = BeautifulSoup(r1.content, "html.parser").find("a", {"style": "vertical-align: top"})
    if link is None or not link.get("name"):
        raise RuntimeError("cjpg: primeira sentença sem atributo name")
    cd_processo, cd_foro, nm_alias, cd_documento = str(link["name"]).split("-")
    time.sleep(1.5)
    resposta = session.get(
        f"{ESAJ_BASE}cjpg/obterArquivo.do",
        params={"cdProcesso": cd_processo, "cdForo": cd_foro, "nmAlias": nm_alias, "cdDocumento": cd_documento},
        allow_redirects=False,
        timeout=60,
    )
    if resposta.status_code != 302:
        raise RuntimeError(f"obterArquivo.do: esperava 302, veio {resposta.status_code}")
    local = resposta.headers["Location"]
    time.sleep(1.5)
    dump(dest / f"pasta_{cd_documento}.html", session.get(local, timeout=60).content)
    dump(dest / "redirecionamentos.json", json.dumps({f"sentenca_{cd_documento}": local}, indent=1).encode())


def _cjpg_primeira_pagina(pesquisa: str) -> bytes:
    session = build_session()
    session.get(f"{ESAJ_BASE}cjpg/open.do", timeout=60)
    resposta = session.get(f"{ESAJ_BASE}cjpg/pesquisar.do", params=make_tjsp_cjpg_params(pesquisa), timeout=60)
    resposta.raise_for_status()
    return resposta.content


def capture_cjpg_sentenca_sem_bens() -> None:
    """Grava ``cjpg/sentenca_nao_foram_encontrados.html``: sentenças que citam "não foram encontrados".

    A frase é um dos marcadores de busca sem resultado. Em 26/11/2026, a busca
    trouxe "Resultados 1 a 10 de 2303", e a contagem dava 0 porque lia o
    texto das sentenças.
    """
    conteudo = _cjpg_primeira_pagina('"não foram encontrados bens"')
    if "não foram encontrados" not in BeautifulSoup(conteudo, "html.parser").get_text():
        # Sem a frase, o sample deixaria de exercitar o caso.
        raise RuntimeError("cjpg sentenca_nao_foram_encontrados: frase ausente na 1a página; troque a busca")
    dump(samples_dir_for("tjms", "cjpg") / "sentenca_nao_foram_encontrados.html", conteudo)


def capture_cjpg_single_page() -> None:
    """Grava ``cjpg/single_page.html``: busca cujos resultados cabem numa página de 10.

    Em 26/11/2026, "machine learning" trouxe 2 sentenças ("Resultados 1 a 2
    de 2"). Confere pelas linhas da página, e não por ``cjpg_n_results``.
    """
    conteudo = _cjpg_primeira_pagina("machine learning")
    linhas = BeautifulSoup(conteudo, "html.parser").select("#divDadosResultado tr.fundocinza1")
    if not 0 < len(linhas) < 10:
        # Com 10 linhas pode haver página 2, e o sample deixaria de exercitar o caso.
        raise RuntimeError(f"cjpg single_page: {len(linhas)} linhas na 1a página; troque a busca")
    dump(samples_dir_for("tjms", "cjpg") / "single_page.html", conteudo)


def main() -> None:
    """Capture cjsg and cjpg samples for TJMS."""
    capture_cjsg_samples(
        tribunal="tjms",
        base_url="https://esaj.tjms.jus.br/",
        # Sem acento: "usucapiao predio rural" dá 0 monocráticas no TJMS e
        # "usucapião rural", 340; "usucapiao" dá 6 (16/11/2026).
        monocratica_query="usucapiao",
    )
    capture_cjpg()
    capture_cjpg_single_page()
    capture_cjpg_sentenca_sem_bens()


if __name__ == "__main__":
    main()
