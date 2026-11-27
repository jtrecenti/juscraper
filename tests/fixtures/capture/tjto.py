"""Capture cjsg + cjpg samples for TJTO.

Run from repo root::

    python -m tests.fixtures.capture.tjto                               # todos os samples
    python -m tests.fixtures.capture.tjto --only cjsg/single_page.html  # só o arquivo citado
    python -m tests.fixtures.capture.tjto --only 'cjpg/*' 'cjsg/ementa_*'

Saves the Solr-style HTML responses for each public method (cjsg, cjpg)
plus two ``ementa_<uuid>.json`` payloads from the ``ementa.php`` endpoint
that powers ``cjsg_ementa(uuid)``.

A captura completa faz 11 buscas e 2 GETs de ementa. O AWS WAF do TJTO
desafia (HTTP 202) a 7ª busca feita do mesmo IP em menos de uns 10 minutos e
só volta a responder depois de uns 15 minutos (CONTRIBUTING.md > Integração
local). Por isso o script espera ``--pausa`` segundos (padrão: 120) entre o
fim de uma requisição e o início da seguinte, e a captura completa leva uns 24
minutos. Medido de IP residencial em 27/11/2026: com 90 s entre as buscas, a
7ª já recebeu o desafio; com 120 s, 14 buscas seguidas passaram, e a captura
completa também. ``--pausa 0`` desliga a espera, o que serve com ``--only`` de
poucos arquivos.

``--only`` recebe um ou mais padrões ``fnmatch`` no formato
``<endpoint>/<arquivo>`` e captura só os samples que casam com algum deles; os
demais ficam como estão. As ementas saem dos dois primeiros UUIDs de
``cjsg/results_normal_page_01.html`` lidos do disco antes de qualquer
requisição (os mesmos que os testes de contrato usam), e não da página que a
própria execução regrava. O desafio do WAF interrompe o script antes de gravar
a resposta, para não sobrescrever um sample bom com a página vazia; depois de
15 minutos, rode de novo com ``--only`` só os arquivos que faltaram no log.
"""
import argparse
import fnmatch
import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from juscraper.core.intervalo import IntervaloEntrePedidos
from juscraper.core.waf import USER_AGENT
from juscraper.courts.tjto.download import BASE_URL, EMENTA_URL, TYPE_MINUTA_MAP, build_cjsg_payload, eh_bloqueio_waf

from ._util import dump, samples_dir_for

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r'data-id="([a-f0-9-]{30,})"')

# Cada item é ``(termo, páginas, arquivos[, tipo_documento])``.
CJSG_QUERIES: list[tuple] = [
    ("dano moral", (1, 2),
     ("results_normal_page_01.html", "results_normal_page_02.html")),
    ("\"alimentos avoengos\"", (1, 3), ("single_page.html", "pagina_alem_do_total.html")),
    ("juscraper_probe_zero_hits_xyzqwe", (1,), ("no_results.html",)),
    # Aba que não é a de acórdãos: o total sai da aba do tipo pedido.
    ("\"alimentos avoengos\"", (1,), ("decisoes_single_page.html",), "decisoes"),
]
CJPG_QUERIES: list[tuple] = [
    ("\"dano moral\"", (1, 2),
     ("results_normal_page_01.html", "results_normal_page_02.html")),
    ("\"despejo\"", (1,), ("single_page.html",)),
    ("juscraper_probe_zero_hits_xyzqwe", (1,), ("no_results.html",)),
    ("\"despejo\"", (1,), ("sentencas_page_01.html",), "sentencas"),
]
# Instância do ``tip_criterio_inst`` de cada endpoint.
ENDPOINTS = {"cjsg": ("2", CJSG_QUERIES), "cjpg": ("1", CJPG_QUERIES)}
PAUSA_PADRAO = 120.0  # segundos entre requisições (docstring do módulo)


def _minify(raw: bytes) -> bytes:
    """Keep only the ``#result`` block (panel-document + total-results tab).

    The full TJTO response is ~1 MB per page; the parser only consumes the
    ``#result`` div (137 KB). The lateral filter sidebar is the bulk of the
    weight and isn't read by either ``_get_total_results`` or
    ``cjsg_parse_manager`` — drop it.
    """
    soup = BeautifulSoup(raw, "html.parser")
    result = soup.select_one("#result")
    if result is None:
        return raw  # nothing to strip — defensive
    return f"<html><body>{result}</body></html>".encode("utf-8")


def _selecionado(nome: str, padroes: list[str] | None) -> bool:
    return padroes is None or any(fnmatch.fnmatch(nome, padrao) for padrao in padroes)


class _SessaoEspacada(requests.Session):
    """Sessão que espera ``pausa`` segundos entre uma requisição e a seguinte."""

    def __init__(self, pausa: float) -> None:
        super().__init__()
        self.pausa = pausa
        self._intervalo = IntervaloEntrePedidos()

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        with self._intervalo.pedido(self.pausa):
            return super().request(*args, **kwargs)


def _conferir_waf(resp: requests.Response, *_args: object, **_kwargs: object) -> None:
    """Interrompe no desafio (HTTP 202) ou no CAPTCHA do AWS WAF, como o raspador."""
    if eh_bloqueio_waf(resp):
        raise SystemExit(
            f"[tjto] o AWS WAF bloqueou {resp.url} (HTTP {resp.status_code}). Espere 15 minutos e rode "
            "de novo com --only os arquivos que ainda não aparecem como 'wrote' no log."
        )


def _post(session: requests.Session, query: str, *, start: int, instancia: str,
          type_minuta: str) -> requests.Response:
    payload = build_cjsg_payload(query, start=start, tip_criterio_inst=instancia, type_minuta=type_minuta)
    response = session.post(BASE_URL, data=payload, timeout=60)
    response.raise_for_status()
    return response


def _capture_endpoint(session: requests.Session, endpoint: str, padroes: list[str] | None) -> None:
    """Grava as páginas de ``endpoint`` cujo ``<endpoint>/<arquivo>`` casa com ``padroes``."""
    instancia, queries = ENDPOINTS[endpoint]
    out = samples_dir_for("tjto", endpoint)
    for query, pages, files, *tipo in queries:
        type_minuta = TYPE_MINUTA_MAP[tipo[0] if tipo else "acordaos"]
        for page, filename in zip(pages, files, strict=True):
            if not _selecionado(f"{endpoint}/{filename}", padroes):
                continue
            start = (page - 1) * 20
            response = _post(session, query, start=start, instancia=instancia, type_minuta=type_minuta)
            stripped = _minify(response.content)
            dump(out / filename, stripped)
            logger.info(
                "[tjto/%s] wrote %s (page=%s, raw=%s, minified=%s)",
                endpoint,
                filename,
                page,
                len(response.content),
                len(stripped),
            )


def _ementa_uuids() -> list[str]:
    """Os dois primeiros UUIDs distintos do sample típico do cjsg, lido do disco."""
    sample = samples_dir_for("tjto", "cjsg") / "results_normal_page_01.html"
    if not sample.exists():
        logger.warning("[tjto/cjsg] sem %s; as ementas ficam de fora", sample.name)
        return []
    html = sample.read_bytes().decode("utf-8", errors="replace")
    return list(dict.fromkeys(_UUID_RE.findall(html)))[:2]


def _capture_ementas(session: requests.Session, uuids: list[str], padroes: list[str] | None) -> None:
    """Capture the ``_fetch_ementa`` payloads of ``uuids``."""
    out = samples_dir_for("tjto", "cjsg")
    for uuid in uuids:
        filename = f"ementa_{uuid}.json"
        if not _selecionado(f"cjsg/{filename}", padroes):
            continue
        response = session.get(EMENTA_URL, params={"id": uuid}, timeout=30)
        response.raise_for_status()
        dump(out / filename, response.content)
        logger.info("[tjto/cjsg] wrote %s (bytes=%s)", filename, len(response.content))


def _alvos(ementa_uuids: list[str]) -> list[str]:
    """Todos os ``<endpoint>/<arquivo>`` que a captura completa grava."""
    alvos = [
        f"{endpoint}/{filename}"
        for endpoint, (_, queries) in ENDPOINTS.items()
        for _query, _pages, files, *_tipo in queries
        for filename in files
    ]
    return alvos + [f"cjsg/ementa_{uuid}.json" for uuid in ementa_uuids]


def main(argv: list[str] | None = None) -> None:
    """Capture cjsg + cjpg + ementa samples for TJTO."""
    parser = argparse.ArgumentParser(description="Captura os samples de cjsg e cjpg do TJTO.")
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="ENDPOINT/ARQUIVO",
        help="Padrões fnmatch (ex.: cjsg/single_page.html, 'cjpg/*'); captura só os samples que casam.",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=PAUSA_PADRAO,
        metavar="SEGUNDOS",
        help=f"Espera entre uma requisição e a seguinte (padrão: {PAUSA_PADRAO:g}).",
    )
    args = parser.parse_args(argv)
    padroes = args.only
    ementa_uuids = _ementa_uuids()
    if padroes:
        alvos = _alvos(ementa_uuids)
        if sem_alvo := [p for p in padroes if not fnmatch.filter(alvos, p)]:
            parser.error(f"nenhum sample casa com {sem_alvo}; opções: {', '.join(alvos)}")

    session = _SessaoEspacada(args.pausa)
    session.headers.update({"User-Agent": USER_AGENT})
    session.hooks["response"].append(_conferir_waf)

    for endpoint in ENDPOINTS:
        _capture_endpoint(session, endpoint, padroes)
    _capture_ementas(session, ementa_uuids, padroes)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
