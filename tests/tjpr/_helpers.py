"""Helpers compartilhados pelos contratos cjsg do TJPR.

A ``home`` GET é idêntica em ``test_cjsg_contract.py``,
``test_cjsg_filters_contract.py`` e ``test_cjsg_corte_idh_contract.py``;
promovida para evitar drift, como ``add_search_page`` (sample fixo + matcher
do corpo) e ``add_ementa_completa``, comuns aos dois contratos de resultado.
``test_cjsg_filters_contract.py`` mantém seu POST local, de assinatura
diferente (sample dinâmico + matcher de página).
"""
from __future__ import annotations

import responses
from responses.matchers import urlencoded_params_matcher

from juscraper.courts.tjpr.download import BASE_URL, SEARCH_URL, build_cjsg_form_body
from tests._helpers import load_sample, query_param_subset_matcher

__all__ = ["SEARCH_URL", "add_ementa_completa", "add_home", "add_search_page"]


def add_home() -> None:
    responses.add(
        responses.GET,
        BASE_URL,
        body=load_sample("tjpr", "cjsg/home.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def add_search_page(pesquisa: str, pagina: int, sample_path: str) -> None:
    responses.add(
        responses.POST,
        SEARCH_URL,
        body=load_sample("tjpr", sample_path),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[
            query_param_subset_matcher({"actionType": "pesquisar"}),
            urlencoded_params_matcher(
                build_cjsg_form_body(pesquisa, page=pagina),
                allow_blank=True,
            ),
        ],
    )


def add_ementa_completa() -> None:
    """Single response shared by every ``actionType=exibirTextoCompleto`` GET.

    As of 2026-04 the upstream endpoint returns a generic Struts error page
    regardless of ``idProcesso``/``criterio``; we capture one and reuse it.
    """
    responses.add(
        responses.GET,
        SEARCH_URL,
        body=load_sample("tjpr", "cjsg/ementa_completa.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
        match=[query_param_subset_matcher({"actionType": "exibirTextoCompleto"})],
    )
