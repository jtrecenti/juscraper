"""Shared helpers for eSAJ sample-capture scripts.

These scripts run against the live eSAJ platform and dump raw HTML/JSON to
``tests/<tribunal>/samples/<endpoint>/`` for use by offline contract tests.
They are NOT run during ``pytest`` — they are maintenance tools, invoked
manually whenever a tribunal changes its layout.

Usage (from repo root)::

    python -m tests.fixtures.capture.tjac
    python -m tests.fixtures.capture.tjsp
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

# Chrome-flavoured UA that the TJSP cjsg_download.py injects. Mirroring it
# here keeps the captured samples bit-identical to what the real scraper
# sends — matters for both contract payload matchers and server-side
# behaviour (eSAJ behaves differently for non-browser UAs).
TJSP_CHROME_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
    ),
}

REPO_ROOT = Path(__file__).resolve().parents[3]


def samples_dir_for(tribunal: str, endpoint: str = "cjsg") -> Path:
    """Return ``tests/<tribunal>/samples/<endpoint>/`` (created if needed)."""
    dest = REPO_ROOT / "tests" / tribunal / "samples" / endpoint
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def make_esaj_body(
    pesquisa: str,
    *,
    tipo_decisao: str = "acordao",
    origem: str = "T",
    ementa: str = "",
    numero_recurso: str = "",
    classe: str = "",
    assunto: str = "",
    comarca: str = "",
    orgao_julgador: str = "",
    data_julgamento_inicio: str = "",
    data_julgamento_fim: str = "",
    data_publicacao_inicio: str = "",
    data_publicacao_fim: str = "",
) -> dict:
    """Build the form body expected by ``cjsg/resultadoCompleta.do`` (eSAJ-puros).

    Mirrors the body built by the 5 eSAJ-puros scrapers
    (TJAC/TJAL/TJAM/TJCE/TJMS) byte-for-byte. All filter parameters are
    optional and default to the same empty-string values the scraper
    sends when the caller doesn't supply them. TJSP has a different
    body shape — use :func:`make_tjsp_cjsg_body` there.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    return {
        "conversationId": "",
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": ementa,
        "dados.nuProcOrigem": numero_recurso,
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
        "classesTreeSelection.values": classe,
        "classesTreeSelection.text": "",
        "assuntosTreeSelection.values": assunto,
        "assuntosTreeSelection.text": "",
        "comarcaSelectedEntitiesList": "",
        "contadorcomarca": "1",
        "contadorMaiorcomarca": "1",
        "cdComarca": comarca,
        "nmComarca": "",
        "secoesTreeSelection.values": orgao_julgador,
        "secoesTreeSelection.text": "",
        "dados.dtJulgamentoInicio": data_julgamento_inicio,
        "dados.dtJulgamentoFim": data_julgamento_fim,
        "dados.dtRegistroInicio": "",
        "dados.dtRegistroFim": "",
        "dados.dtPublicacaoInicio": data_publicacao_inicio,
        "dados.dtPublicacaoFim": data_publicacao_fim,
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
        "dados.ordenacao": "dtPublicacao",
    }


def make_tjsp_cjsg_body(
    pesquisa: str,
    *,
    tipo_decisao: str = "acordao",
    baixar_sg: bool = True,
    ementa: str = "",
    classe: str = "",
    assunto: str = "",
    comarca: str = "",
    orgao_julgador: str = "",
    data_inicio: str = "",
    data_fim: str = "",
) -> dict:
    """Build the form body sent by the TJSP cjsg scraper.

    Mirrors ``src/juscraper/courts/tjsp/forms.py::build_tjsp_cjsg_body`` so
    contract matchers can assert payload equality. Differences from the
    eSAJ-puros body: no ``conversationId``/``dtPublicacao*``; the
    ``*TreeSelection`` fields carry filter values rather than empty strings;
    ``origem`` is ``'T'`` when ``baixar_sg`` is ``True``, else ``'R'``.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    origem = "T" if baixar_sg else "R"
    return {
        "dados.buscaInteiroTeor": pesquisa,
        "dados.pesquisarComSinonimos": "S",
        "dados.buscaEmenta": ementa,
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
        "classesTreeSelection.values": classe,
        "classesTreeSelection.text": "",
        "assuntosTreeSelection.values": assunto,
        "assuntosTreeSelection.text": "",
        "comarcaSelectedEntitiesList": "",
        "contadorcomarca": "1",
        "contadorMaiorcomarca": "1",
        "cdComarca": comarca,
        "nmComarca": "",
        "secoesTreeSelection.values": orgao_julgador,
        "secoesTreeSelection.text": "",
        "dados.dtJulgamentoInicio": data_inicio,
        "dados.dtJulgamentoFim": data_fim,
        "dados.dtRegistroInicio": "",
        "dados.dtRegistroFim": "",
        "dados.ordenacao": "dtPublicacao",
        "dados.origensSelecionadas": origem,
        "tipoDecisaoSelecionados": tipo_param,
    }


def make_tjsp_cjpg_params(
    pesquisa: str,
    *,
    id_processo: str = "",
    classes: list[str] | None = None,
    assuntos: list[str] | None = None,
    varas: list[str] | None = None,
    data_inicio: str = "",
    data_fim: str = "",
) -> dict:
    """Build the query params sent to ``cjpg/pesquisar.do`` on TJSP.

    Mirrors ``src/juscraper/courts/tjsp/cjpg_download.py::cjpg_download``.
    ``id_processo`` is assumed already normalized (via ``clean_cnj``) — this
    helper does not normalize, to keep contract tests close to real HTTP.
    """
    classes_str = ",".join(classes) if classes else None
    assuntos_str = ",".join(assuntos) if assuntos else None
    varas_str = ",".join(varas) if varas else None
    return {
        "conversationId": "",
        "dadosConsulta.pesquisaLivre": pesquisa,
        "tipoNumero": "UNIFICADO",
        "numeroDigitoAnoUnificado": id_processo[:15],
        "foroNumeroUnificado": id_processo[-4:] if id_processo else "",
        "dadosConsulta.nuProcesso": id_processo,
        "classeTreeSelection.values": classes_str,
        "assuntoTreeSelection.values": assuntos_str,
        "dadosConsulta.dtInicio": data_inicio or None,
        "dadosConsulta.dtFim": data_fim or None,
        "varasTreeSelection.values": varas_str,
        "dadosConsulta.ordenacao": "DESC",
    }


def build_session(
    adapters: dict | None = None,
    headers: dict | None = None,
) -> requests.Session:
    """Build a ``requests.Session`` with eSAJ headers preset.

    ``adapters`` lets TJCE attach its ``SECLEVEL=1`` adapter without this
    helper importing scraper-internal modules. ``headers`` overrides the
    default UA (e.g., TJSP uses Chrome flavour).
    """
    session = requests.Session()
    session.headers.update(headers or ESAJ_HEADERS)
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
    body_builder=None,
) -> tuple[requests.Response, list[requests.Response]]:
    """Submit a cjsg query and fetch the requested pages.

    Mirrors the eSAJ scrapers' two-step flow (POST form, then GETs). Caller
    decides which responses to save — this helper is agnostic. Override
    ``body_builder`` to use ``make_tjsp_cjsg_body`` instead of the default.
    """
    tipo_param = "A" if tipo_decisao == "acordao" else "D"
    post_url = f"{base_url}cjsg/resultadoCompleta.do"
    builder = body_builder or make_esaj_body
    body = builder(pesquisa, tipo_decisao=tipo_decisao)

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
    headers: dict | None = None,
    body_builder=None,
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
    refresh breaks the default. TJSP passes ``body_builder=make_tjsp_cjsg_body``
    and ``headers=TJSP_CHROME_HEADERS`` because its scraper sends a different
    body/UA.
    """
    dest = samples_dir_for(tribunal, "cjsg")
    session = build_session(adapters=adapters, headers=headers)

    post_resp, get_resps = fetch_cjsg_pages(
        session, base_url, typical_query, paginas=typical_pages, body_builder=body_builder
    )
    dump(dest / "post_initial.html", post_resp.content)
    for pag, resp in zip(typical_pages, get_resps):
        dump(dest / f"results_normal_page_{pag:02d}.html", resp.content)  # noqa: E231
    print(f"[{tribunal}] typical ({typical_query!r}) → {len(get_resps)} page(s)")

    _, single_resps = fetch_cjsg_pages(
        session, base_url, single_page_query, paginas=(1,), body_builder=body_builder
    )
    dump(dest / "single_page.html", single_resps[0].content)
    print(f"[{tribunal}] single_page ({single_page_query!r}) → saved")

    _, none_resps = fetch_cjsg_pages(
        session, base_url, no_results_query, paginas=(1,), body_builder=body_builder
    )
    dump(dest / "no_results.html", none_resps[0].content)
    print(f"[{tribunal}] no_results ({no_results_query!r}) → saved")

    print(f"[{tribunal}] ALL samples written to {dest}")
