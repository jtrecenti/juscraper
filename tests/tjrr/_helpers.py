"""Helpers compartilhados pelos contratos cjsg do TJRR.

Funções aqui são reusadas entre ``test_cjsg_contract.py`` e
``test_cjsg_filters_contract.py`` para evitar duplicação. Mantemos como
módulo importável (e não como ``conftest.py``) porque são funções
utilitárias, não fixtures pytest.
"""
from __future__ import annotations

import re

import responses

from tests._helpers import load_sample

INDEX_URL = "https://jurisprudencia.tjrr.jus.br/index.xhtml"


def add_get_initial() -> None:
    """Registra o GET inicial em ``/index.xhtml``.

    Primeira leg de toda chamada ``cjsg``. O conteúdo capturado contém o
    ``ViewState`` e os IDs JSF dinâmicos (``menuinicial:j_idtNNN``) que o
    scraper precisa para montar o body.
    """
    responses.add(
        responses.GET,
        INDEX_URL,
        body=load_sample("tjrr", "cjsg/step_01_consulta.html"),
        status=200,
        content_type="text/html; charset=UTF-8",
    )


def get_pesquisa_field_name() -> str:
    """Lê do sample o nome JSF dinâmico do campo de busca.

    Retorna algo como ``menuinicial:j_idt28`` — o número JSF muda se o
    sample for re-capturado contra um deploy diferente do TJRR. Usar
    esta função desacopla os asserts do número específico hoje.
    """
    sample = load_sample("tjrr", "cjsg/step_01_consulta.html")
    match = re.search(
        r'name="(menuinicial:j_idt\d+)"[^>]*id="consultaAtual"',
        sample,
    )
    if not match:
        raise RuntimeError(
            "campo de pesquisa (id=consultaAtual) não encontrado em "
            "tests/tjrr/samples/cjsg/step_01_consulta.html"
        )
    return match.group(1)
