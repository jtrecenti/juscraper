"""Shared helpers for eSAJ sample-capture scripts.

These scripts run against the live eSAJ platform and dump raw HTML to
``tests/<tribunal>/samples/cjsg/`` for use by offline contract tests. They
are NOT run during ``pytest`` — they are maintenance tools, invoked manually
whenever a tribunal changes its HTML layout.

Usage (from repo root)::

    python -m tests.fixtures.capture.tjac
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import requests

ESAJ_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "juscraper/0.1 (https://github.com/jtrecenti/juscraper)",
}

REPO_ROOT = Path(__file__).resolve().parents[3]


def samples_dir_for(tribunal: str) -> Path:
    """Return ``tests/<tribunal>/samples/cjsg/`` (created if needed)."""
    dest = REPO_ROOT / "tests" / tribunal / "samples" / "cjsg"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def make_esaj_body(
    pesquisa: str,
    *,
    tipo_decisao: str = "acordao",
    origem: str = "T",
) -> dict:
    """Build the form body expected by ``cjsg/resultadoCompleta.do``.

    Mirrors the body built by ``src/juscraper/courts/<tribunal>/cjsg_download.py``
    so captured HTMLs reflect real scraper submissions.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    return {
        "conversationId": "",
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": "",
        "dados.nuProcOrigem": "",
        "dados.nuRegistro": "",
        "agenteSelectedEntitiesList": "",
        "contadoragente": "0",
        "contadorMaioragente": "0",
        "codigoCr": "",
        "codigoTr": "",
        "nmAgente": "",
        "juizProlatorSelectedEntitiesList": "",
        "contadorjuizProlator": "0",
        "contadorMaiorjuizProlator": "0",
        "codigoJuizCr": "",
        "codigoJuizTr": "",
        "nmJuiz": "",
        "classesTreeSelection.values": "",
        "classesTreeSelection.text": "",
        "assuntosTreeSelection.values": "",
        "assuntosTreeSelection.text": "",
        "comarcaSelectedEntitiesList": "",
        "contadorcomarca": "1",
        "contadorMaiorcomarca": "1",
        "cdComarca": "",
        "nmComarca": "",
        "secoesTreeSelection.values": "",
        "secoesTreeSelection.text": "",
        "dados.dtJulgamentoInicio": "",
        "dados.dtJulgamentoFim": "",
        "dados.dtRegistroInicio": "",
        "dados.dtRegistroFim": "",
        "dados.dtPublicacaoInicio": "",
        "dados.dtPublicacaoFim": "",
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
        "dados.ordenacao": "dtPublicacao",
    }


def build_session(adapters: dict | None = None) -> requests.Session:
    """Build a ``requests.Session`` with eSAJ headers preset.

    ``adapters`` lets TJCE attach its ``SECLEVEL=1`` adapter without this
    helper importing scraper-internal modules.
    """
    session = requests.Session()
    session.headers.update(ESAJ_HEADERS)
    if adapters:
        for prefix, adapter in adapters.items():
            session.mount(prefix, adapter)
    return session


def fetch_cjsg_pages(
    session: requests.Session,
    base_url: str,
    pesquisa: str,
    paginas: Iterable[int] = (1,),
    *,
    tipo_decisao: str = "acordao",
    timeout: int = 60,
) -> tuple[requests.Response, list[requests.Response]]:
    """Submit a cjsg query and fetch the requested pages.

    Mirrors the eSAJ scrapers' two-step flow (POST form, then GETs). Caller
    decides which responses to save — this helper is agnostic.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    post_url = f"{base_url}cjsg/resultadoCompleta.do"
    body = make_esaj_body(pesquisa, tipo_decisao=tipo_decisao)

    post_resp = session.post(post_url, data=body, timeout=timeout, allow_redirects=True)
    post_resp.raise_for_status()

    get_responses: list[requests.Response] = []
    get_url = f"{base_url}cjsg/trocaDePagina.do"
    for pag in paginas:
        r = session.get(
            get_url,
            params={"tipoDeDecisao": tipo_param, "pagina": str(pag)},
            headers={"Accept": "text/html; charset=latin1;", "Referer": post_url},
            timeout=timeout,
        )
        r.encoding = "latin1"
        r.raise_for_status()
        get_responses.append(r)

    return post_resp, get_responses


def dump(path: Path, data: bytes) -> None:
    """Write raw bytes to ``path``, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def capture_cjsg_samples(
    tribunal: str,
    base_url: str,
    *,
    adapters: dict | None = None,
    typical_query: str = "dano moral",
    single_page_query: str = "usucapiao extraordinario predio rural familia",
    no_results_query: str = "juscraper_probe_zero_hits_xyzqwe",
    typical_pages: tuple[int, ...] = (1, 2),
) -> None:
    """Run three canonical cjsg queries and dump raw HTML.

    Writes to ``tests/<tribunal>/samples/cjsg/``:

    - ``post_initial.html`` — POST response (reused across scenarios)
    - ``results_normal_page_NN.html`` — typical multi-page
    - ``single_page.html`` — query whose hits fit in one page (n_pags == 1)
    - ``no_results.html`` — zero-hit page

    Defaults are hand-picked to yield ≤20 hits across the five eSAJ courts
    in scope (TJAC/TJAL/TJAM/TJCE/TJMS). Override per-script if a layout
    refresh breaks the default.
    """
    dest = samples_dir_for(tribunal)
    session = build_session(adapters=adapters)

    post_resp, get_resps = fetch_cjsg_pages(
        session, base_url, typical_query, paginas=typical_pages
    )
    dump(dest / "post_initial.html", post_resp.content)
    for pag, resp in zip(typical_pages, get_resps):
        dump(dest / f"results_normal_page_{pag:02d}.html", resp.content)  # noqa: E231
    print(f"[{tribunal}] typical ({typical_query!r}) → {len(get_resps)} page(s)")

    _, single_resps = fetch_cjsg_pages(session, base_url, single_page_query, paginas=(1,))
    dump(dest / "single_page.html", single_resps[0].content)
    print(f"[{tribunal}] single_page ({single_page_query!r}) → saved")

    _, none_resps = fetch_cjsg_pages(session, base_url, no_results_query, paginas=(1,))
    dump(dest / "no_results.html", none_resps[0].content)
    print(f"[{tribunal}] no_results ({no_results_query!r}) → saved")

    print(f"[{tribunal}] ALL samples written to {dest}")
