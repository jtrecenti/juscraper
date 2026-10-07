"""Mock da sequência de requisições do ``cjsg`` do TRF3 para os contratos.

A busca abre a aba da base (``GET home/index/{n}``), envia o formulário
(``POST Home/ResultadoTotais``, que responde 302 para a página 1) e lê as
demais páginas em ``GET Home/ListaResumida/2?np=N``. Os corpos vêm dos samples
capturados por ``tests/fixtures/capture/trf3_cjsg.py``; o 302 é o único
corpo sintético, porque o ``requests`` só precisa do ``Location``.
"""
from __future__ import annotations

import responses
from responses.matchers import query_param_matcher, urlencoded_params_matcher

from juscraper.courts.trf3.cjsg_download import BASE_URL, BASES, INDEX_URL, PAGE_URL, SEARCH_URL
from tests._helpers import load_sample_bytes

FIRST_PAGE_URL = BASE_URL + "Home/ListaResumida/1"
REDIRECT_LOCATION = "/jurisprudencia/Home/ListaResumida/1?np=0"
HTML = "text/html; charset=utf-8"


def sample(nome: str) -> bytes:
    return load_sample_bytes("trf3", f"cjsg/{nome}")


def add_search(payload: dict[str, str], first_page: str, *, base: str = "acordaos") -> None:
    """Registra o GET de abertura, o POST (exato) e a página 1."""
    indice = BASES[base][0]
    responses.add(
        responses.GET,
        INDEX_URL.format(indice=indice),
        body=sample("index_acordaos.html"),
        status=200,
        content_type=HTML,
    )
    responses.add(
        responses.POST,
        SEARCH_URL,
        status=302,
        headers={"Location": REDIRECT_LOCATION},
        match=[urlencoded_params_matcher(payload, allow_blank=True)],
    )
    responses.add(
        responses.GET,
        FIRST_PAGE_URL,
        body=sample(first_page),
        status=200,
        content_type=HTML,
        match=[query_param_matcher({"np": "0"})],
    )


def add_page(pagina: int, nome: str) -> None:
    responses.add(
        responses.GET,
        PAGE_URL,
        body=sample(nome),
        status=200,
        content_type=HTML,
        match=[query_param_matcher({"np": str(pagina)})],
    )
