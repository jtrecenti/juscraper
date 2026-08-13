"""Contract tests (offline) para o agregador Falcao.

Validam, sem tocar a rede (``responses``):

- schema do DataFrame devolvido por ``cjsg`` (colunas canonicas garantidas);
- que a querystring enviada carrega as guardas obrigatorias do backend
  (``colecao``, ``sessionId``, ``page`` 0-based, ``size``);
- que kwargs desconhecidos viram ``TypeError`` e filtros invalidos viram
  ``ValidationError`` — ambos **antes** de qualquer request.
"""
import json

import pandas as pd
import pytest
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.aggregators.falcao.download import SEARCH_URL
from tests._helpers import assert_unknown_kwarg_raises, load_sample


def _sample(colecao: str, cenario: str = "normal") -> dict:
    return json.loads(load_sample("falcao", f"pesquisa/{colecao}_{cenario}.json"))


def _register(colecao: str, cenario: str = "normal", *, total: int | None = None):
    """Registra o endpoint devolvendo o sample da colecao.

    ``total`` sobrescreve ``quantidadeTotal`` para controlar a paginacao
    (default: 1 pagina, para nao disparar mil requests).
    """
    body = _sample(colecao, cenario)
    if total is not None:
        body["quantidadeTotal"] = total
    else:
        body["quantidadeTotal"] = len(body["documentos"])
    responses.add(responses.GET, SEARCH_URL, json=body, status=200)


@pytest.fixture
def falcao():
    return jus.scraper("falcao", verbose=0, sleep_time=0)


@responses.activate
def test_cjsg_schema_colunas_canonicas(falcao):
    _register("acordaos")
    df = falcao.cjsg("dano moral", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    for coluna in ("processo", "colecao", "tribunal"):
        assert coluna in df.columns
    assert (df["colecao"] == "acordaos").all()


@responses.activate
def test_cjsg_querystring_guardas_obrigatorias(falcao):
    _register("acordaos")
    falcao.cjsg("dano moral", paginas=1, tamanho_pagina=5)
    req = responses.calls[0].request
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(req.url).query)
    assert qs["colecao"] == ["acordaos"]
    assert qs["texto"] == ["dano moral"]
    assert qs["page"] == ["0"]  # 1-based publico -> 0-based backend
    assert qs["size"] == ["5"]
    assert qs["sessionId"][0].startswith("_")  # guarda anti-acesso


@responses.activate
@pytest.mark.parametrize(
    "colecao", ["sentencas", "decisoesmonocraticas", "precedentes", "recursorevista"]
)
def test_cjsg_todas_colecoes_parseiam(falcao, colecao):
    _register(colecao)
    df = falcao.cjsg("dano moral", paginas=1, colecao=colecao)
    assert len(df) == 2
    assert (df["colecao"] == colecao).all()
    assert df["processo"].notna().all()


@responses.activate
def test_cjsg_resultado_vazio(falcao):
    _register("acordaos", "vazio")
    df = falcao.cjsg("termosemresultado", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_filtros_viram_querystring(falcao):
    _register("acordaos")
    falcao.cjsg(
        "dano moral",
        paginas=1,
        tribunais=["TST", "TRT3"],
        relator="FULANO",
        classe=["ROT"],
        tem_ementa=True,
        somente_ementa=False,
        ordenacao="mais_recente",
        data_juntada_inicio="01/01/2024",
        data_juntada_fim="2024-06-30",
    )
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(responses.calls[0].request.url).query)
    assert qs["tribunais"] == ["TST,TRT3"]
    assert qs["nomeRelator"] == ["FULANO"]
    assert qs["classeProcesso"] == ["ROT"]
    assert qs["temEmenta"] == ["true"]
    assert qs["pesquisaSomenteNasEmentas"] == ["false"]
    assert qs["ordenacao"] == ["mais_recente"]
    # datas BR e ISO ambas convertidas para ISO
    assert qs["dataInicio"] == ["2024-01-01"]
    assert qs["dataFim"] == ["2024-06-30"]


def test_kwarg_desconhecido_vira_typeerror(falcao):
    # Nao precisa de mock: raise_on_extra_kwargs dispara antes de qualquer request.
    assert_unknown_kwarg_raises(falcao.cjsg, "parametro_bobo", "dano moral", paginas=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"colecao": "inexistente"},
        {"tamanho_pagina": 20},
        {"ordenacao": "aleatorio"},
    ],
)
def test_filtro_invalido_vira_validationerror(falcao, kwargs):
    with pytest.raises(ValidationError):
        falcao.cjsg("dano moral", paginas=1, **kwargs)
