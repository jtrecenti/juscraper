"""Contract tests (offline) para o agregador Falcao.

Validam, sem tocar a rede (``responses``):

- schema do DataFrame devolvido por ``cjsg`` (colunas canonicas garantidas);
- que a querystring enviada carrega as guardas obrigatorias do backend
  (``colecao``, ``sessionId``, ``page`` 0-based, ``size``) e todos os filtros;
- a paginacao (varias paginas, ``range`` com passo, pagina 1 fora do pedido);
- que kwargs desconhecidos viram ``TypeError`` e filtros invalidos viram
  ``ValidationError``/``ValueError`` — todos **antes** de qualquer request;
- que bloqueios definitivos do backend (WAF, 429 de horas) nao sao retentados.
"""
import json
from pathlib import Path

import pandas as pd
import pytest
import requests
import responses
from pydantic import ValidationError

import juscraper as jus
from juscraper.aggregators.falcao import client as falcao_client
from juscraper.aggregators.falcao.download import SEARCH_URL
from juscraper.core.exceptions import BotChallengeBlockedError
from tests._helpers import assert_unknown_kwarg_raises, load_sample, query_param_subset_matcher


def _sample(colecao: str, cenario: str = "normal") -> dict:
    return json.loads(load_sample("falcao", f"pesquisa/{colecao}_{cenario}.json"))


def _register(amostra: str = "acordaos", cenario: str = "normal", *, total: int | None = None,
              pagina: int | None = None, **params):
    """Registra o endpoint devolvendo o sample da colecao ``amostra``.

    ``total`` sobrescreve ``quantidadeTotal`` para controlar quantas paginas
    o client enxerga (default: so os documentos do sample, uma pagina).
    ``pagina`` (1-based) e ``params`` viram matcher da querystring, para que
    cada pagina so responda a requisicao certa.
    """
    body = _sample(amostra, cenario)
    body["quantidadeTotal"] = len(body["documentos"]) if total is None else total
    esperado = {k: str(v) for k, v in params.items()}
    if pagina is not None:
        esperado["page"] = str(pagina - 1)
    matchers = [query_param_subset_matcher(esperado)] if esperado else []
    responses.add(responses.GET, SEARCH_URL, json=body, status=200, match=matchers)


def _paginas_pedidas() -> list[int]:
    from urllib.parse import parse_qs, urlparse

    return [int(parse_qs(urlparse(c.request.url).query)["page"][0]) + 1 for c in responses.calls]


@pytest.fixture
def falcao():
    return jus.scraper("falcao", verbose=0, sleep_time=0)


@responses.activate
def test_cjsg_schema_colunas_canonicas(falcao):
    _register("acordaos")
    df = falcao.cjsg("dano moral", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == len(_sample("acordaos")["documentos"])
    for coluna in ("processo", "colecao", "tribunal", "relator", "classe", "classe_sigla", "ementa"):
        assert coluna in df.columns
    assert (df["colecao"] == "acordaos").all()
    assert not [c for c in df.columns if c.startswith("highlight")]


@responses.activate
def test_cjsg_querystring_guardas_obrigatorias(falcao):
    _register("acordaos", colecao="acordaos", texto="dano moral", page=0, size=5)
    falcao.cjsg("dano moral", paginas=1, tamanho_pagina=5)
    assert len(responses.calls) == 1
    assert falcao.session_id in responses.calls[0].request.url


@responses.activate
@pytest.mark.parametrize(
    "colecao", ["sentencas", "decisoesmonocraticas", "precedentes", "recursorevista"]
)
def test_cjsg_todas_colecoes_parseiam(falcao, colecao):
    _register(colecao, colecao=colecao)
    df = falcao.cjsg("dano moral", paginas=1, colecao=colecao)
    assert len(df) == len(_sample(colecao)["documentos"])
    assert (df["colecao"] == colecao).all()
    assert df["processo"].notna().all()
    assert df["processo"].is_unique


@responses.activate
def test_cjsg_resultado_vazio(falcao):
    _register("acordaos", "vazio")
    df = falcao.cjsg("termosemresultado", paginas=1)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate
def test_cjsg_todos_os_filtros_viram_querystring(falcao):
    _register(
        "acordaos",
        tribunais="TST,TRT3",
        nomeRelator="FULANO",
        orgaoJulgador="1ª Turma,2ª Turma",
        classeProcesso="ROT",
        faseProcessual="CONHECIMENTO",
        prioridade="IDOSO",
        temEmenta="true",
        pesquisaSomenteNasEmentas="false",
        ordenacao="mais_recente",
        dataInicio="2024-01-01",
        dataFim="2024-06-30",
        size=10,
        colecao="acordaos",
    )
    falcao.cjsg(
        "dano moral",
        paginas=1,
        colecao="acordaos",
        tamanho_pagina=10,
        tribunais=["TST", "TRT3"],
        relator="FULANO",
        orgao_julgador=["1ª Turma", "2ª Turma"],
        classe=["ROT"],
        fase_processual="CONHECIMENTO",
        prioridade=["IDOSO"],
        tem_ementa=True,
        somente_ementa=False,
        ordenacao="mais_recente",
        data_juntada_inicio="01/01/2024",  # BR e ISO, ambas convertidas para ISO
        data_juntada_fim="2024-06-30",
    )
    assert len(responses.calls) == 1


@responses.activate
def test_cjsg_pagina_varias_paginas(falcao, tmp_path):
    # 25 resultados em paginas de 10: tres paginas, a ultima parcial.
    for pagina in (1, 2, 3):
        _register("acordaos", total=25, pagina=pagina)
    pasta = Path(falcao.cjsg_download("dano moral", paginas=None, diretorio=str(tmp_path)))
    assert _paginas_pedidas() == [1, 2, 3]
    assert sorted(p.name for p in pasta.iterdir()) == [
        "acordaos_0001.json", "acordaos_0002.json", "acordaos_0003.json",
    ]


@responses.activate
def test_cjsg_range_com_passo_respeita_o_passo(falcao):
    for pagina in (1, 3, 5):
        _register("acordaos", total=100, pagina=pagina)
    falcao.cjsg("dano moral", paginas=range(1, 6, 2))
    assert _paginas_pedidas() == [1, 3, 5]


@responses.activate
def test_cjsg_sem_pagina_1_nao_a_requisita(falcao):
    for pagina in (2, 3):
        _register("acordaos", total=100, pagina=pagina)
    df = falcao.cjsg("dano moral", paginas=[2, 3])
    assert _paginas_pedidas() == [2, 3]
    assert len(df) == 2 * len(_sample("acordaos")["documentos"])


@responses.activate
@pytest.mark.parametrize("paginas", [[1.0, 2.0], ["1", "2"]])
def test_cjsg_paginas_coagidas_pelo_schema(falcao, paginas):
    for pagina in (1, 2):
        _register("acordaos", total=100, pagina=pagina)
    df = falcao.cjsg("dano moral", paginas=paginas)
    assert _paginas_pedidas() == [1, 2]
    assert len(df) == 2 * len(_sample("acordaos")["documentos"])


@responses.activate
def test_cjsg_avisa_quando_atinge_o_teto(falcao, monkeypatch):
    # Teto reduzido para 20 para o teste nao precisar de mil paginas.
    monkeypatch.setattr(falcao_client, "_MAX_RESULTADOS", 20)
    for pagina in (1, 2):
        _register("acordaos", total=20, pagina=pagina)
    with pytest.warns(UserWarning, match="teto de 20 resultados"):
        falcao.cjsg("dano moral")
    assert _paginas_pedidas() == [1, 2]


@responses.activate
def test_cjsg_nao_avisa_com_paginas_explicitas(falcao, monkeypatch):
    monkeypatch.setattr(falcao_client, "_MAX_RESULTADOS", 20)
    _register("acordaos", total=20, pagina=1)
    falcao.cjsg("dano moral", paginas=1)  # filterwarnings=error: warning viraria falha


@responses.activate
def test_downloads_no_mesmo_diretorio_nao_se_misturam(falcao, tmp_path):
    # Mesma colecao, segunda busca menor que a primeira: com pasta fixa, a
    # pagina 1 da segunda sobrescrevia so o _0001.json e o parse devolvia
    # tambem a pagina 2 da primeira.
    por_pagina = len(_sample("acordaos")["documentos"])
    for pagina in (1, 2):
        _register("acordaos", total=100, pagina=pagina, texto="dano moral")
    _register("acordaos", total=100, pagina=1, texto="assedio")
    pasta_a = falcao.cjsg_download("dano moral", paginas=2, diretorio=str(tmp_path))
    pasta_b = falcao.cjsg_download("assedio", paginas=1, diretorio=str(tmp_path))
    assert pasta_a != pasta_b
    assert Path(pasta_a).parent == Path(pasta_b).parent == tmp_path
    assert len(falcao.cjsg_parse(pasta_a)) == 2 * por_pagina
    assert len(falcao.cjsg_parse(pasta_b)) == por_pagina
    # A pasta-mae junta as duas buscas (leitura recursiva).
    assert len(falcao.cjsg_parse(tmp_path)) == 3 * por_pagina


@responses.activate
def test_cjsg_download_sem_diretorio_usa_download_path(tmp_path):
    scraper = jus.scraper("falcao", verbose=0, sleep_time=0, download_path=str(tmp_path))
    _register("acordaos")
    pasta = scraper.cjsg_download("dano moral", paginas=1)
    assert Path(pasta).parent == tmp_path


def test_cjsg_rejeita_diretorio(falcao):
    with pytest.raises(TypeError, match=r"'diretorio'.*cjsg_download"):
        falcao.cjsg("dano moral", paginas=1, diretorio="out")


@responses.activate
@pytest.mark.parametrize("alias", ["query", "termo"])
def test_alias_deprecado_de_pesquisa(falcao, alias):
    _register("acordaos", texto="dano moral")
    with pytest.warns(DeprecationWarning, match=alias):
        df = falcao.cjsg(paginas=1, **{alias: "dano moral"})
    assert not df.empty


def test_pesquisa_e_alias_juntos_levantam(falcao):
    with pytest.raises(ValueError, match="pesquisa"):
        falcao.cjsg("dano moral", paginas=1, query="outra")


def test_kwarg_desconhecido_vira_typeerror(falcao):
    # Nao precisa de mock: raise_on_extra_kwargs dispara antes de qualquer request.
    assert_unknown_kwarg_raises(falcao.cjsg, "parametro_bobo", "dano moral", paginas=1)


def test_kwarg_desconhecido_no_download_cita_o_metodo_certo(falcao, tmp_path):
    with pytest.raises(TypeError, match=r"cjsg_download\(\)"):
        falcao.cjsg_download("dano moral", paginas=1, diretorio=str(tmp_path), parametro_bobo=1)
    assert not list(tmp_path.iterdir())


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


@responses.activate  # sem endpoint registrado: qualquer request falharia com ConnectionError
@pytest.mark.parametrize("campo", ["data_juntada_inicio", "data_juntada_fim"])
@pytest.mark.parametrize("valor", ["abc", "", "31/02/2024"])
def test_data_invalida_isolada_vira_valueerror(falcao, campo, valor):
    with pytest.raises(ValueError, match=campo):
        falcao.cjsg("dano moral", paginas=1, **{campo: valor})
    assert not responses.calls


def test_intervalo_invertido_vira_valueerror(falcao):
    with pytest.raises(ValueError, match="posterior"):
        falcao.cjsg("dano moral", paginas=1, data_juntada_inicio="2024-02-01", data_juntada_fim="2024-01-01")


@responses.activate
def test_data_isolada_valida_vai_para_o_backend(falcao):
    _register("acordaos", dataInicio="2024-01-31")
    falcao.cjsg("dano moral", paginas=1, data_juntada_inicio="31/01/2024")
    assert len(responses.calls) == 1


@responses.activate
def test_waf_cloudfront_nao_e_retentado(falcao):
    responses.add(
        responses.GET, SEARCH_URL, status=403, content_type="text/html",
        body="<HTML><TITLE>ERROR: The request could not be satisfied</TITLE></HTML>",
        headers={"Server": "CloudFront"},
    )
    with pytest.raises(BotChallengeBlockedError):
        falcao.cjsg("dano moral", paginas=1)
    assert len(responses.calls) == 1


@responses.activate
def test_429_de_horas_nao_e_retentado(falcao):
    responses.add(
        responses.GET, SEARCH_URL, status=429, json={"userMessage": "Too Many Requests"},
        headers={"x-rate-limit-retry-after-seconds": "20880"},
    )
    with pytest.raises(requests.HTTPError, match="429"):
        falcao.cjsg("dano moral", paginas=1)
    assert len(responses.calls) == 1
