"""Filter propagation, deprecated aliases and payload shape for STF listar_decisoes."""
import pytest
import responses

import juscraper as jus
from juscraper.courts.stf.download import build_payload, traduzir_operadores
from tests.stf._collection_helpers import Source, add_sample, make_rows

PESQUISA = "juscraper_probe_zero_hits_xyzqwe"


def _add_no_results(**payload_kwargs) -> None:
    add_sample("no_results.json", **payload_kwargs)


@pytest.fixture
def stf():
    return jus.scraper("stf", waf_token="token-de-teste")


@responses.activate
def test_todos_os_filtros_chegam_ao_corpo(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=100,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01012024",
        data_julgamento_fim="31122024",
        data_publicacao_inicio="01022024",
        data_publicacao_fim="30112024",
    )

    stf.listar_decisoes(
        PESQUISA,
        paginas=1,
        tamanho_pagina=100,
        base="acordaos",
        classe=["Rcl", "ARE"],
        inteiro_teor=True,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
        data_publicacao_inicio="01/02/2024",
        data_publicacao_fim="30/11/2024",
    )

    assert len(responses.calls) == 3


@responses.activate
def test_alias_query_vira_pesquisa(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(pesquisa=PESQUISA, pagina=1, tamanho_pagina=250)

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(query=PESQUISA, paginas=1)


@responses.activate
def test_alias_data_inicio_fim_vira_data_julgamento(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=250,
        data_julgamento_inicio="01012024",
        data_julgamento_fim="31122024",
    )

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(PESQUISA, paginas=1, data_inicio="01/01/2024", data_fim="31/12/2024")


@responses.activate
def test_alias_termo_vira_pesquisa(stf, mocker):
    mocker.patch("time.sleep")
    _add_no_results(pesquisa=PESQUISA, pagina=1, tamanho_pagina=250)

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(termo=PESQUISA, paginas=1)


@pytest.mark.parametrize(
    "aliases,campo",
    [
        ({"data_julgamento_de": "01/01/2024", "data_julgamento_ate": "31/12/2024"}, "julgamento"),
        ({"data_publicacao_de": "01/01/2024", "data_publicacao_ate": "31/12/2024"}, "publicacao"),
    ],
)
@responses.activate
def test_aliases_de_ate_viram_datas_canonicas(stf, mocker, aliases, campo):
    mocker.patch("time.sleep")
    _add_no_results(
        pesquisa=PESQUISA,
        pagina=1,
        tamanho_pagina=250,
        **{f"data_{campo}_inicio": "01012024", f"data_{campo}_fim": "31122024"},
    )

    with pytest.warns(DeprecationWarning):
        stf.listar_decisoes(PESQUISA, paginas=1, **aliases)


def test_kwarg_desconhecido_levanta_type_error(stf):
    with pytest.raises(TypeError, match="ministro"):
        stf.listar_decisoes(PESQUISA, ministro="GILMAR MENDES")


@pytest.mark.parametrize("metodo", ["listar_decisoes", "contar_decisoes"])
@pytest.mark.parametrize("eixo", ["julgamento", "publicacao"])
@responses.activate
def test_intervalo_plurianual_preserva_os_limites(stf, mocker, metodo, eixo):
    mocker.patch("time.sleep")
    fonte = Source(make_rows(2, start="2021-01-01")).install()
    filtros = {f"data_{eixo}_inicio": "2020-01-01", f"data_{eixo}_fim": "2022-01-01"}

    resultado = getattr(stf, metodo)(PESQUISA, **filtros)

    if metodo == "listar_decisoes":
        assert len(resultado) == 2
    else:
        assert resultado.loc[resultado.faceta == "total", "n"].item() == 2
    for corpo in fonte.payloads:
        assert {"range": {f"{eixo}_data": {"format": "ddMMyyyy", "from": "01012020", "lte": "01012022"}}} in (
            corpo["query"]["function_score"]["query"]["bool"]["filter"]
        )


@pytest.mark.parametrize("metodo", ["listar_decisoes", "contar_decisoes"])
@pytest.mark.parametrize("eixo", ["julgamento", "publicacao"])
@pytest.mark.parametrize("limite", ["inicio", "fim"])
@responses.activate
def test_data_isolada_valida_nao_preenche_outro_limite(stf, mocker, metodo, eixo, limite):
    mocker.patch("time.sleep")
    fonte = Source(make_rows(1, start="1988-01-01")).install()

    getattr(stf, metodo)(PESQUISA, **{f"data_{eixo}_{limite}": "1988-01-01"})

    operador = "from" if limite == "inicio" else "lte"
    for corpo in fonte.payloads:
        intervalos = [
            filtro["range"]
            for filtro in corpo["query"]["function_score"]["query"]["bool"]["filter"]
            if "range" in filtro
        ]
        assert intervalos == [{f"{eixo}_data": {"format": "ddMMyyyy", operador: "01011988"}}]


@pytest.mark.parametrize("metodo", ["listar_decisoes", "contar_decisoes"])
@pytest.mark.parametrize("eixo", ["julgamento", "publicacao"])
@pytest.mark.parametrize("limite", ["inicio", "fim"])
@pytest.mark.parametrize("data", ["31/02/2024", "2024-02-30", "invalida"])
@responses.activate
def test_data_isolada_invalida_falha_antes_de_efeitos(stf, mocker, tmp_path, metodo, eixo, limite, data):
    renovar = mocker.patch.object(stf, "_renovar_token")
    diretorio = tmp_path / "checkpoint"
    filtros = {f"data_{eixo}_{limite}": data}
    if metodo == "listar_decisoes":
        filtros["checkpoint_dir"] = diretorio

    with pytest.raises(ValueError, match=f"data_{eixo}"):
        getattr(stf, metodo)(PESQUISA, **filtros)

    renovar.assert_not_called()
    assert not responses.calls
    assert not diretorio.exists()


@pytest.mark.parametrize("metodo", ["listar_decisoes", "contar_decisoes"])
@pytest.mark.parametrize("eixo", ["julgamento", "publicacao"])
@responses.activate
def test_intervalo_invertido_continua_rejeitado(stf, metodo, eixo):
    with pytest.raises(ValueError, match="posterior"):
        getattr(stf, metodo)(
            PESQUISA, **{f"data_{eixo}_inicio": "2022-01-01", f"data_{eixo}_fim": "2020-01-01"}
        )
    assert not responses.calls


def test_build_payload_aplica_filtros_como_o_portal():
    body = build_payload(
        "terceiriz$ ou pejotização",
        pagina=3,
        tamanho_pagina=50,
        base="acordaos",
        classe="Rcl",
        inteiro_teor=True,
        data_publicacao_fim="20082023",
    )
    consulta = body["query"]["function_score"]["query"]["bool"]

    assert consulta["filter"][0]["query_string"]["query"] == "terceiriz* OR pejotização"
    assert all(c["query_string"]["query"] == "terceiriz* OR pejotização" for c in consulta["should"])
    assert "inteiro_teor_texto.plural" in consulta["filter"][0]["query_string"]["fields"]
    assert "inteiro_teor_texto.plural^0.5" in consulta["should"][1]["query_string"]["fields"]
    assert consulta["filter"][1] == {"range": {"publicacao_data": {"format": "ddMMyyyy", "lte": "20082023"}}}
    filtro_classe = {"terms": {"processo_classe_processual_unificada_classe_sigla.keyword": ["Rcl"]}}
    assert body["post_filter"]["bool"]["must"] == [{"term": {"base": "acordaos"}}, filtro_classe]
    assert filtro_classe in body["aggs"]["ministro_facet_agg"]["filter"]["bool"]["must"]
    agg_classe = body["aggs"]["processo_classe_processual_unificada_classe_sigla_agg"]
    assert filtro_classe not in agg_classe["filter"]["bool"]["must"]
    assert (body["from"], body["size"]) == (100, 50)


def test_build_payload_with_only_start_date():
    body = build_payload(data_julgamento_inicio="01012024")
    filters = body["query"]["function_score"]["query"]["bool"]["filter"]
    assert filters[-1] == {"range": {"julgamento_data": {"format": "ddMMyyyy", "from": "01012024"}}}


def test_build_payload_sem_pesquisa_busca_tudo_e_encurta_ultima_pagina():
    body = build_payload(pagina=1429, tamanho_pagina=7)
    assert body["query"]["function_score"]["query"]["bool"]["filter"][0]["query_string"]["query"] == "*"
    assert (body["from"], body["size"]) == (9996, 4)


@pytest.mark.parametrize("base", ["decisoes", "acordaos"])
def test_build_payload_desempata_score_por_id_sem_mutar_o_template(base):
    build_payload(base=base)
    assert build_payload(base=base)["sort"] == [{"_score": "desc"}, {"id": "asc"}]


@pytest.mark.parametrize(
    "digitado,enviado",
    [
        # Pares observados no corpo que o portal envia para a API.
        ("direito e privacidade", "direito AND privacidade"),
        ("prisão não preventiva", "prisão NOT preventiva"),
        ("$constitucional", "*constitucional"),
        ("RE 56394?", "RE 56394?"),
        ("direito E (privacidade OU intimidade)", "direito AND (privacidade OR intimidade)"),
        ("terceirização ou terceiriz$", "terceirização OR terceiriz*"),
        # Operador so vale como palavra solta e fora de aspas.
        ("ouvidoria ou contrato", "ouvidoria OR contrato"),
        ('presunção de "não" culpabilidade', 'presunção de "não" culpabilidade'),
        ('"direito e dever$" ou multa', '"direito e dever$" OR multa'),
    ],
)
def test_traduzir_operadores_como_o_portal(digitado, enviado):
    assert traduzir_operadores(digitado) == enviado
