"""Prova ao vivo de que cada filtro do ``cjsg`` do TJRS restringe o resultado.

O contrato offline (``test_cjsg_filters_contract.py``) confere só que o filtro
chega ao body. Aqui, para cada filtro, a mesma pesquisa roda sem e com ele: o
total com o filtro precisa ser positivo e menor que o total sem, e os
documentos da primeira página precisam trazer o valor filtrado no campo bruto
do Solr (a lista inteira, nos campos multivalorados, e não só o primeiro valor
que o parser guarda). Os valores de classe, assunto, órgão julgador, relator e
tipo de processo vêm de documentos reais dos samples em
``tests/tjrs/samples/cjsg/`` (os quatro primeiros como código ``cod_*``, que é
o que o portal aceita); a seção e os intervalos de data foram escolhidos
para cair fora do que os samples trazem (seção cível, datas de 2026).

O ``www.tjrs.jus.br`` não aceita conexão de IP de datacenter (timeout de
conexão); rode de IP residencial. ``--log-cli-level=INFO`` mostra a tabela
filtro -> total sem e com o filtro -> documentos conferidos, e o ``q`` que o
Solr recebeu (o portal acrescenta o filtro ao ``q``, não usa ``fq``)::

    uv run pytest -m integration tests/tjrs/test_cjsg_filters_integration.py --log-cli-level=INFO
"""
from __future__ import annotations

import logging
from typing import Any

import pytest

from juscraper.courts.tjrs.client import TJRSScraper

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)

PESQUISA = "dano moral"

#: Filtro -> (kwargs do ``cjsg``, campos brutos que precisam conter o valor filtrado).
FILTROS: dict[str, tuple[dict[str, str], tuple[str, ...]]] = {
    # Classe, assunto, órgão e relator vão por código: Recurso Inominado,
    # Indenização por Dano Material, Primeira Turma Recursal Cível e
    # José Ricardo de Bem Sanhudo nos samples.
    "classe": ({"classe": "460"}, ("cod_classe_cnj",)),
    "assunto": ({"assunto": "7780"}, ("cod_assunto_cnj",)),
    "orgao_julgador": ({"orgao_julgador": "65"}, ("cod_org_julg",)),
    # O filtro pode casar com o relator ou com o redator do acórdão.
    "relator": ({"relator": "650"}, ("cod_relator", "cod_redator")),
    "tipo_processo": ({"tipo_processo": "Mandado de Segurança Cível"}, ("tipo_processo",)),
    "secao": ({"secao": "crime"}, ("secao",)),
    "data_julgamento": (
        {"data_julgamento_inicio": "01/03/2024", "data_julgamento_fim": "31/03/2024"},
        ("data_julgamento",),
    ),
    "data_publicacao": (
        {"data_publicacao_inicio": "01/03/2024", "data_publicacao_fim": "31/03/2024"},
        ("data_publicacao",),
    ),
}

#: Intervalo, em ISO, dos filtros de data acima.
INTERVALO_DATAS = ("2024-03-01", "2024-03-31")


def _confere(doc: dict[str, Any], nome: str) -> bool:
    filtro, campos = FILTROS[nome]
    valores: list[object] = []
    for campo in campos:
        valor = doc.get(campo)
        valores.extend(v for v in (valor if isinstance(valor, list) else [valor]) if v is not None)
    if nome.startswith("data_"):
        # ``2024-03-01T03:00:00Z`` é a meia-noite de Brasília em UTC: a data é o prefixo.
        inicio, fim = INTERVALO_DATAS
        return any(inicio <= str(v)[:10] <= fim for v in valores)
    # A seção vem em caixa alta (``CRIME``); os demais valores, como nos samples.
    (esperado,) = filtro.values()
    return any(str(v).casefold() == esperado.casefold() for v in valores)


@pytest.fixture(scope="module")
def scraper() -> TJRSScraper:
    return TJRSScraper()


@pytest.fixture(scope="module")
def total_sem_filtro(scraper: TJRSScraper) -> int:
    return int(scraper.cjsg_download(PESQUISA, paginas=1)[0]["response"]["numFound"])


@pytest.mark.parametrize("nome", list(FILTROS))
def test_filtro_restringe_o_resultado(scraper: TJRSScraper, total_sem_filtro: int, nome: str) -> None:
    filtro, campos = FILTROS[nome]
    bruto = scraper.cjsg_download(PESQUISA, paginas=1, **filtro)[0]
    total_com = int(bruto["response"]["numFound"])
    docs: list[dict[str, Any]] = bruto["response"]["docs"]
    fora = [
        {campo: doc.get(campo) for campo in ("numero_processo", *campos)} for doc in docs if not _confere(doc, nome)
    ]
    q = bruto.get("responseHeader", {}).get("params", {}).get("q")
    logger.info(
        "TJRS cjsg %s: sem=%s com=%s conferidos=%s/%s q=%s",
        nome, total_sem_filtro, total_com, len(docs) - len(fora), len(docs), q,
    )

    assert 0 < total_com < total_sem_filtro, f"{nome}: o filtro não restringiu ({total_com} de {total_sem_filtro})"
    assert docs
    assert not fora, f"{nome}: documentos sem o valor filtrado: {fora}"
