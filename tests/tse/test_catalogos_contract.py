"""Contratos offline dos catálogos do TSE (classes, relatores, eleições e normas)."""
import json

import pytest
import responses
from responses import matchers

import juscraper as jus
from juscraper.core.exceptions import InvalidJSONResponseError
from juscraper.courts.tse.download import PESQUISA_URL
from juscraper.courts.tse.parse import CatalogoInesperadoError
from tests._helpers import load_sample_bytes

# Método público, sub-rota do portal e colunas do DataFrame.
CATALOGOS = [
    ("listar_classes", "classes", ["sigla_classe", "descricao_classe"]),
    ("listar_relatores", "relatorias", ["relator"]),
    ("listar_eleicoes", "eleicoes", ["eleicao"]),
    ("listar_normas", "normas", ["sigla", "tipo", "numero", "ano", "norma"]),
]


def _corpo_lista_vazia(request):
    # A rota responde HTTP 500 sem o corpo ``[]``.
    return request.body in (b"[]", "[]"), f"corpo enviado: {request.body!r}"


def _registrar(sub_rota: str, **resposta) -> None:
    responses.add(
        responses.POST,
        f"{PESQUISA_URL}/{sub_rota}",
        match=[_corpo_lista_vazia, matchers.header_matcher({"Content-Type": "application/json"})],
        **resposta,
    )


@responses.activate
@pytest.mark.parametrize(("metodo", "sub_rota", "colunas"), CATALOGOS)
def test_catalogo_devolve_uma_linha_por_item(metodo, sub_rota, colunas):
    corpo = load_sample_bytes("tse", f"catalogos/{sub_rota}.json")
    _registrar(sub_rota, body=corpo, content_type="application/json")

    df = getattr(jus.scraper("tse"), metodo)()

    assert list(df.columns) == colunas
    assert len(df) == len(json.loads(corpo)) > 0
    assert df.notna().all().all()


@responses.activate
def test_classes_e_normas_preservam_os_valores_do_portal():
    _registrar("classes", body=load_sample_bytes("tse", "catalogos/classes.json"), content_type="application/json")
    _registrar("normas", body=load_sample_bytes("tse", "catalogos/normas.json"), content_type="application/json")
    tse = jus.scraper("tse")

    classes = tse.listar_classes()
    normas = tse.listar_normas()

    assert classes.iloc[0].to_dict() == {"sigla_classe": "RESPE", "descricao_classe": "Recurso Especial Eleitoral"}
    # O portal manda a descrição com espaço no fim; ela sai como veio.
    assert "Agravo em Recurso Especial Eleitoral " in set(classes["descricao_classe"])
    assert normas.iloc[0][["sigla", "tipo", "numero", "ano"]].to_dict() == {
        "sigla": "EC117", "tipo": "EMENDA CONSTITUCIONAL", "numero": "117", "ano": "2022",
    }


@responses.activate
def test_eleicoes_saem_em_texto_como_no_portal():
    _registrar("eleicoes", body=load_sample_bytes("tse", "catalogos/eleicoes.json"), content_type="application/json")

    df = jus.scraper("tse").listar_eleicoes()

    assert df["eleicao"].tolist()[:3] == ["2026", "2024", "2022"]


@responses.activate
@pytest.mark.parametrize(("metodo", "sub_rota", "colunas"), CATALOGOS)
def test_catalogo_vazio_mantem_as_colunas(metodo, sub_rota, colunas):
    _registrar(sub_rota, json=[])

    df = getattr(jus.scraper("tse"), metodo)()

    assert df.empty
    assert list(df.columns) == colunas


@responses.activate
@pytest.mark.parametrize(("metodo", "sub_rota", "_colunas"), CATALOGOS)
def test_envelope_de_erro_nao_vira_catalogo_vazio(metodo, sub_rota, _colunas):
    # Resposta real da busca sem token, em 16/11/2026: JSON válido, mas não é catálogo.
    _registrar(
        sub_rota,
        json={"mensagem": "Falha na verificação antirrobô.", "content": [], "totalRegistros": 0, "aggs": []},
    )

    with pytest.raises(CatalogoInesperadoError, match="antirrobô"):
        getattr(jus.scraper("tse"), metodo)()


@responses.activate
def test_itens_de_tipo_trocado_sao_recusados():
    _registrar("relatorias", body=load_sample_bytes("tse", "catalogos/classes.json"), content_type="application/json")

    with pytest.raises(CatalogoInesperadoError, match="relatorias"):
        jus.scraper("tse").listar_relatores()


@responses.activate
def test_chave_nova_do_backend_entra_depois_das_colunas_conhecidas():
    _registrar("classes", json=[{"novaChave": 1, "siglaClasse": "RESPE", "descricaoClasse": "Recurso Especial"}])

    df = jus.scraper("tse").listar_classes()

    assert list(df.columns) == ["sigla_classe", "descricao_classe", "novaChave"]


@responses.activate
def test_corpo_sem_json_levanta_erro_com_contexto(mocker):
    mocker.patch("time.sleep")
    _registrar("classes", body="<html>erro</html>", content_type="text/html")

    with pytest.raises(InvalidJSONResponseError):
        jus.scraper("tse").listar_classes()

    assert len(responses.calls) == 3


@responses.activate
def test_timeout_do_perfil_e_ajustavel_por_politica(mocker):
    _registrar("eleicoes", json=["2026"])
    tse = jus.scraper("tse", politica={"catalogo": {"timeout": 7}})
    pedido = mocker.spy(tse.session, "request")

    tse.listar_eleicoes()

    assert pedido.call_args.kwargs["timeout"] == 7
    assert jus.scraper("tse")._perfis_http["catalogo"].timeout == 60  # noqa: SLF001  # default do perfil
