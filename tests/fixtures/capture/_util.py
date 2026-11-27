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

import logging
import warnings
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

import juscraper as jus
from juscraper.courts._esaj.acordao import AcordaoIndisponivelError

# Mesmos headers que o raspador eSAJ manda, importados para que os samples
# capturados continuem batendo com o que ele recebe se o cliente mudar. O TJSP
# usa o UA de Chrome (``CJSG_CHROME_UA``): o eSAJ responde diferente a UAs que
# não são de navegador, e os matchers de payload dos contratos dependem disso.
from juscraper.courts._esaj.download import _CHROME_HEADERS as TJSP_CHROME_HEADERS
from juscraper.courts._esaj.download import _ESAJ_HEADERS as ESAJ_HEADERS
from juscraper.courts._esaj.parse import _total_declarado

logger = logging.getLogger(__name__)

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

    Mirrors ``src/juscraper/courts/_esaj/cjpg_download.py::cjpg_download``.
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


def fetch_cjpg_page1(session: requests.Session, base_url: str, pesquisa: str) -> requests.Response:
    """Primeira página do cjpg do eSAJ (TJSP e TJMS) para ``pesquisa``.

    Passa antes por ``cjpg/open.do``, que grava o JSESSIONID e os cookies
    que o servidor passou a exigir de consultas anônimas. O raspador não faz
    isso, mas o navegador faz.
    """
    session.get(f"{base_url}cjpg/open.do", timeout=60)
    resposta = session.get(f"{base_url}cjpg/pesquisar.do", params=make_tjsp_cjpg_params(pesquisa), timeout=60)
    resposta.raise_for_status()
    return resposta


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
    monocratica_query: str | None = None,
) -> None:
    """Run the canonical cjsg queries and dump raw HTML.

    Writes to ``tests/<tribunal>/samples/cjsg/``:

    - ``post_initial.html`` — POST response (reused across scenarios)
    - ``results_normal_page_NN.html`` — typical multi-page
    - ``single_page.html`` — query whose hits fit in one page (n_pags == 1)
    - ``no_results.html`` — zero-hit page
    - ``monocratica_single_page.html`` — se ``monocratica_query`` for dada,
      ver :func:`capture_cjsg_monocratica_sample`

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
    for pag, resp in zip(typical_pages, get_resps, strict=False):
        dump(dest / f"results_normal_page_{pag:02d}.html", resp.content)
    logger.info("[%s] typical (%r) → %s page(s)", tribunal, typical_query, len(get_resps))

    _, single_resps = fetch_cjsg_pages(
        session, base_url, single_page_query, paginas=(1,), body_builder=body_builder
    )
    dump(dest / "single_page.html", single_resps[0].content)
    logger.info("[%s] single_page (%r) → saved", tribunal, single_page_query)

    _, none_resps = fetch_cjsg_pages(
        session, base_url, no_results_query, paginas=(1,), body_builder=body_builder
    )
    dump(dest / "no_results.html", none_resps[0].content)
    logger.info("[%s] no_results (%r) → saved", tribunal, no_results_query)

    if monocratica_query is not None:
        capture_cjsg_monocratica_sample(session, tribunal, base_url, monocratica_query, body_builder=body_builder)

    logger.info("[%s] ALL samples written to %s", tribunal, dest)


def capture_cjsg_monocratica_sample(
    session: requests.Session,
    tribunal: str,
    base_url: str,
    pesquisa: str,
    *,
    body_builder=None,
) -> None:
    """Capture the 1st cjsg page of a monocratic-decision search.

    Grava ``tests/<tribunal>/samples/cjsg/monocratica_single_page.html``. A
    página de decisões monocráticas traz o total no input
    ``totalResultadoAbaRetornoFiltro-D``, e não no ``-A`` dos acórdãos.
    ``pesquisa`` precisa dar de 1 a 20 resultados (uma página); fora disso,
    ou sem o input ``-D``, nada é gravado.
    """
    _, resps = fetch_cjsg_pages(session, base_url, pesquisa, tipo_decisao="monocratica", body_builder=body_builder)
    soup = BeautifulSoup(resps[0].text, "html.parser")
    # Mesma leitura de ``cjsg_n_results``: só o input ``-D``, sem a cascata.
    n_results = _total_declarado(soup) if soup.select_one("input#totalResultadoAbaRetornoFiltro-D") else None
    if n_results is None or not 1 <= n_results <= 20:
        logger.warning(
            "[%s] cjsg monocratica_single_page (%r): sem o input -D com 1 a 20 resultados (lido: %s); nada gravado",
            tribunal,
            pesquisa,
            n_results,
        )
        return
    dump(samples_dir_for(tribunal, "cjsg") / "monocratica_single_page.html", resps[0].content)
    logger.info("[%s] cjsg monocratica_single_page (%r, %s resultados) → saved", tribunal, pesquisa, n_results)


def capture_acordao_samples(
    tribunal: str,
    casos: Iterable[tuple[str, str, str]],
) -> None:
    """Capture the movimentação route of ``baixar_acordao`` for each case.

    Runs the real ``jus.scraper(tribunal).baixar_acordao`` with a response
    hook that dumps every page to ``tests/<tribunal>/samples/acordao/<cenario>/``
    under a deterministic name, so the contract tests can register the same
    URLs offline. ``casos`` is ``(cenario, cnj, data_julgamento)``. The PDF
    itself is not saved: the tests only need a body starting with ``%PDF``.
    Expected failures (``AcordaoIndisponivelError``) are printed, since some
    cases exist to capture the error pages.
    """
    for cenario, cnj, data_julgamento in casos:
        dest = samples_dir_for(tribunal, f"acordao/{cenario}")
        paginas: dict[str, int] = {}
        ultimo_documento: list[str] = []

        def _gravar(
            resposta: requests.Response,
            *_args: object,
            _dest: Path = dest,
            _paginas: dict[str, int] = paginas,
            _ultimo: list[str] = ultimo_documento,
            **_kwargs: object,
        ) -> None:
            url = urlparse(resposta.request.url or "")
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            rota = url.path.rsplit("/", 1)[-1]
            if rota == "search.do":
                nome = "search.html"
            elif rota == "show.do":
                nome = f"show_{query['processo.codigo']}.html"
            elif rota == "carregarMovimentacoesAjax.do":
                cd = query["cdProcesso"]
                indice = _paginas[cd] = _paginas.get(cd, -1) + 1
                nome = f"movimentacoes_{cd}_{indice}.html"
            elif rota == "verificarAcessoMovimentacao.do":
                _ultimo[:] = [query["cdDocumento"]]
                nome = f"verificar_acesso_{query['cdProcesso']}_{query['cdDocumento']}.html"
            elif rota == "abrirDocumentoEdt.do":
                nome = f"pasta_{query['cdProcesso']}_{_ultimo[0]}.html"
            else:
                return
            dump(_dest / nome, resposta.content)

        scraper = jus.scraper(tribunal)
        scraper.session.hooks["response"].append(_gravar)
        try:
            caminho = scraper.baixar_acordao(cnj, data_julgamento)
            logger.info("[%s] acordao/%s: %s %s -> %s", tribunal, cenario, cnj, data_julgamento, caminho)
        except AcordaoIndisponivelError as erro:
            logger.info(
                "[%s] acordao/%s: %s %s -> %s: %s", tribunal, cenario, cnj, data_julgamento, type(erro).__name__, erro
            )


class _ComCpopg(Protocol):
    """Raspador com sessão ``requests`` e ``cpopg_download`` (PJe dos TRFs e do TJPE, eproc do TRF6)."""

    session: requests.Session

    def cpopg_download(self, id_cnj: str, /) -> list[str | None]:
        """HTML do detalhe de cada CNJ."""


@contextmanager
def respostas_da_sessao(session: requests.Session) -> Iterator[list[requests.Response]]:
    """Guarda, por um hook na sessão, cada resposta que ela receber dentro do bloco."""
    respostas: list[requests.Response] = []

    def guardar(resp: requests.Response, *_args: object, **_kwargs: object) -> None:
        respostas.append(resp)

    session.hooks["response"].append(guardar)
    try:
        yield respostas
    finally:
        session.hooks["response"].remove(guardar)


def respostas_do_cpopg(
    scraper: _ComCpopg,
    cnj: str,
    descartar: Callable[[requests.Response], bool] = lambda _resp: False,
) -> tuple[str | None, list[requests.Response]]:
    """Roda o ``cpopg_download`` de um raspador e devolve o detalhe e as respostas que ele usou.

    As respostas vêm de um hook na sessão. Ficam de fora os erros que o retry
    repetiu, os saltos de redirecionamento e o que ``descartar`` apontar (o
    desafio do WAF, no TJPE): sobra a resposta final de cada requisição.
    """
    with respostas_da_sessao(scraper.session) as respostas, warnings.catch_warnings():
        # Falha da consulta vira ``UserWarning`` no raspador; aqui ela interrompe a captura.
        warnings.filterwarnings("error", category=UserWarning)
        (html,) = scraper.cpopg_download(cnj)
    return html, [r for r in respostas if r.ok and not r.is_redirect and not descartar(r)]


def rotas(respostas: list[requests.Response]) -> list[str]:
    """``MÉTODO url`` de cada resposta, sem a query string."""
    return [f"{r.request.method} {(r.request.url or '').split('?')[0]}" for r in respostas]
