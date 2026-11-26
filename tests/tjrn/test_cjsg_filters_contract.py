"""Filter-propagation contract for TJRN cjsg.

``id_classe`` is the canonical kwarg in ``TJRNScraper.cjsg`` (refs #129).
The legacy ``id_classe_judicial`` alias is still accepted and emits
``DeprecationWarning`` for one version. The backend PJe payload keeps
the original field name (``id_classe_judicial``) — that is an internal
detail of the PJe API and not exposed in the public signature.
"""
import json

import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.matchers import json_params_matcher

import juscraper as jus
from juscraper.courts.tjrn.download import BASE_URL, build_cjsg_payload
from tests._helpers import assert_unknown_kwarg_raises, load_sample


@responses.activate
def test_cjsg_all_filters_land_in_json_body(mocker):
    """Every public filter must reach the POST JSON payload via ``build_cjsg_payload``.

    ``data_julgamento_inicio``/``fim`` arrive in ISO at the public method but
    ``TJRNScraper`` rewrites them as ``DD-MM-YYYY`` (with dashes) before
    passing to ``cjsg_download_manager`` — the backend silently drops any
    other format. See ``_to_tjrn_date`` in ``courts/tjrn/client.py``.

    Note: ``TJRNScraper.cjsg`` exposes only ``data_julgamento_inicio``/``fim``;
    ``data_publicacao_*`` is not in the public signature, so the publication
    date filter does not enter the matcher.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            page=1,
            nr_processo="00000000000000000000",
            id_classe="123",
            id_orgao_julgador="456",
            id_relator="789",
            id_colegiado="10",
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
            sistema="PJE",
            decisoes="Acórdão",
            jurisdicoes="TJ",
            grau="2",
        ))],
    )

    df = jus.scraper("tjrn").cjsg(
        "dano moral",
        paginas=1,
        numero_processo="00000000000000000000",
        id_classe="123",
        id_orgao_julgador="456",
        id_relator="789",
        id_colegiado="10",
        data_julgamento_inicio="2024-01-01",
        data_julgamento_fim="2024-03-31",
        sistema="PJE",
        decisoes="Acórdão",
        jurisdicoes="TJ",
        grau="2",
    )

    assert isinstance(df, pd.DataFrame)
    # O matcher deriva do builder; os nomes de campo do PJe ficam pinados aqui.
    assert json.loads(responses.calls[0].request.body) == {
        "jurisprudencia": {
            "ementa": "dano moral",
            "inteiro_teor": "",
            "nr_processo": "00000000000000000000",
            "id_classe_judicial": "123",
            "id_orgao_julgador": "456",
            "id_relator": "789",
            "id_colegiado": "10",
            "id_juiz": "",
            "id_vara": "",
            "dt_inicio": "01-01-2024",
            "dt_fim": "31-03-2024",
            "origem": "",
            "sistema": "PJE",
            "decisoes": "Acórdão",
            "jurisdicoes": "TJ",
            "grau": "2",
        },
        "page": 1,
        "usuario": {"matricula": "", "token": ""},  # nosec
    }


@responses.activate
def test_cjsg_query_alias_emits_deprecation_warning(mocker):
    """The deprecated ``query`` alias is normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        df = jus.scraper("tjrn").cjsg(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_termo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``termo`` alias is also normalized before the request body is built."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="termo.*deprecado"):
        df = jus.scraper("tjrn").cjsg(pesquisa=None, termo="dano moral", paginas=1)

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_nr_processo_alias_emits_deprecation_warning(mocker):
    """The deprecated ``nr_processo`` alias maps to ``numero_processo`` and
    lands in the payload as ``nr_processo``."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", page=1, nr_processo="00000000000000000000",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="nr_processo.*numero_processo"):
        df = jus.scraper("tjrn").cjsg(
            "dano moral",
            paginas=1,
            nr_processo="00000000000000000000",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_id_classe_judicial_alias_emits_deprecation_warning(mocker):
    """The deprecated ``id_classe_judicial`` alias maps to ``id_classe`` and
    the backend body keeps the ``id_classe_judicial`` field (refs #129)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral", page=1, id_classe="123",
        ))],
    )

    with pytest.warns(DeprecationWarning, match="id_classe_judicial.*id_classe"):
        df = jus.scraper("tjrn").cjsg(
            "dano moral",
            paginas=1,
            id_classe_judicial="123",
        )

    assert isinstance(df, pd.DataFrame)


@responses.activate
def test_cjsg_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``data_inicio``/``data_fim`` generic aliases map to
    ``data_julgamento_inicio``/``data_julgamento_fim`` via ``normalize_datas``,
    are rewritten as ``DD-MM-YYYY`` by ``_to_tjrn_date`` (TJRN's backend
    silently ignores other formats) and reach the BFF payload as
    ``dt_inicio``/``dt_fim``.
    """
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            page=1,
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        df = jus.scraper("tjrn").cjsg(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(df, pd.DataFrame)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)


# (valor de ``decisoes``, sample, termo, filtros extras do payload). Monocraticas e
# sentencas nao tem ementa no portal, e ``pesquisa`` busca so na ementa: os
# samples desses tipos foram capturados sem termo, recortados por periodo.
_DECISOES_CASES = [
    ("Acórdão", "decisoes_acordao.json", "dano moral", {}),
    ("Decisão", "decisoes_decisao.json", "", {"dt_inicio": "01-11-2026", "dt_fim": "20-11-2026"}),
    ("Sentença", "decisoes_sentenca.json", "", {"dt_inicio": "01-11-2026", "dt_fim": "20-11-2026"}),
]


@pytest.mark.parametrize(
    ("decisoes", "sample", "pesquisa", "extras"), _DECISOES_CASES, ids=[c[0] for c in _DECISOES_CASES],
)
@responses.activate
def test_cjsg_decisoes_envia_valor_do_portal(mocker, decisoes, sample, pesquisa, extras):
    """``decisoes`` vai ao payload com o valor do seletor do portal, que o backend
    compara com ``tipo_teor``; os samples confirmam que cada valor traz so o
    tipo pedido."""
    mocker.patch("time.sleep")
    raw = load_sample("tjrn", f"cjsg/{sample}")
    hits = json.loads(raw)["hits"]["hits"]
    assert hits
    assert {h["_source"]["tipo_teor"] for h in hits} == {decisoes}
    responses.add(
        responses.POST,
        BASE_URL,
        body=raw,
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            pesquisa, page=1, decisoes=decisoes, **extras,
        ))],
    )

    df = jus.scraper("tjrn").cjsg(
        pesquisa,
        paginas=1,
        decisoes=decisoes,
        data_julgamento_inicio="2026-11-01" if extras else None,
        data_julgamento_fim="2026-11-20" if extras else None,
    )

    assert json.loads(responses.calls[0].request.body)["jurisprudencia"]["decisoes"] == decisoes
    assert len(df) == len(hits)


@pytest.mark.parametrize("valor", ["Monocraticas", "Colegiadas", "Sentencas", "Acordao"])
def test_cjsg_decisoes_fora_do_portal_levanta_validation_error(valor):
    """Os valores que a docstring indicava (``"Monocraticas"``, ``"Colegiadas"``,
    ``"Sentencas"``) nunca existiram no portal e davam 0 resultados sem aviso;
    agora levantam ``ValidationError`` antes de qualquer requisicao."""
    with pytest.raises(ValidationError, match="decisoes"):
        jus.scraper("tjrn").cjsg("dano moral", paginas=1, decisoes=valor)


# Colegiados das Turmas Recursais e da Turma de Uniformizacao, que ``"TR"`` traz e
# ``"TJ"`` exclui.
_TURMAS = ("Turma Recursal", "Turma de Uniformização")


@pytest.mark.parametrize(
    ("jurisdicoes", "sample", "eh_turma"),
    [("TJ", "jurisdicoes_tj.json", False), ("TR", "jurisdicoes_tr.json", True)],
)
@responses.activate
def test_cjsg_jurisdicoes_envia_valor_do_portal(mocker, jurisdicoes, sample, eh_turma):
    """``jurisdicoes`` vai ao payload com o valor do seletor do portal (``"TJ"``
    ou ``"TR"``); os samples confirmam que cada valor traz so colegiados da
    jurisdicao pedida."""
    mocker.patch("time.sleep")
    raw = load_sample("tjrn", f"cjsg/{sample}")
    responses.add(
        responses.POST,
        BASE_URL,
        body=raw,
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1, jurisdicoes=jurisdicoes))],
    )

    df = jus.scraper("tjrn").cjsg("dano moral", paginas=1, jurisdicoes=jurisdicoes)

    assert json.loads(responses.calls[0].request.body)["jurisprudencia"]["jurisdicoes"] == jurisdicoes
    assert len(df) == len(json.loads(raw)["hits"]["hits"]) > 0
    assert all(any(t in c for t in _TURMAS) == eh_turma for c in df["colegiado"])


@pytest.mark.parametrize("valor", ["Tribunal de Justica", "Turmas Recursais", "tj", "Todas"])
def test_cjsg_jurisdicoes_fora_do_portal_levanta_validation_error(valor):
    """Os valores que a docstring indicava (``"Tribunal de Justica"``,
    ``"Turmas Recursais"``) nunca existiram no portal, que respondia 502/503
    ate esgotar as tentativas; agora levantam ``ValidationError`` antes de
    qualquer requisicao."""
    with pytest.raises(ValidationError, match="jurisdicoes"):
        jus.scraper("tjrn").cjsg("dano moral", paginas=1, jurisdicoes=valor)


def test_cjsg_unknown_kwarg_raises():
    """Kwargs not declared in :class:`InputCJSGTJRN` raise ``TypeError`` with
    the field name, instead of being silently dropped (refs #84, #93)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrn").cjsg,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


def test_cjsg_data_publicacao_raises_typeerror():
    """TJRN backend Elasticsearch nao expoe filtro de data de publicacao —
    ``InputCJSGTJRN`` herda apenas :class:`DataJulgamentoMixin`, entao
    ``data_publicacao_*`` deve cair como ``extra_forbidden`` -> ``TypeError``
    em vez de ser silently dropped (refs #186)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrn").cjsg,
        "data_publicacao_inicio",
        "dano moral",
        paginas=1,
    )


def test_cjsg_alias_conflict_raises():
    """Passar canonical e alias deprecado simultaneamente leva a ``ValueError``."""
    with pytest.raises(ValueError, match=r"numero_processo.*nr_processo"):
        jus.scraper("tjrn").cjsg(
            "dano moral", paginas=1,
            numero_processo="X", nr_processo="Y",
        )


def test_cjsg_download_unknown_kwarg_raises():
    """``cjsg_download`` rejects unknown kwargs at the lower-level entry point
    too — guards against silent drop when the caller skips :meth:`cjsg` (refs #183)."""
    assert_unknown_kwarg_raises(
        jus.scraper("tjrn").cjsg_download,
        "kwarg_inventado",
        "dano moral",
        paginas=1,
    )


@responses.activate
def test_cjsg_download_query_alias_emits_deprecation_warning(mocker):
    """``cjsg_download`` direto consome ``query`` -> ``pesquisa`` via pipeline (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload("dano moral", page=1))],
    )

    with pytest.warns(DeprecationWarning, match="query.*deprecado"):
        result = jus.scraper("tjrn").cjsg_download(pesquisa=None, query="dano moral", paginas=1)

    assert isinstance(result, list)


@responses.activate
def test_cjsg_download_data_inicio_alias_maps_to_data_julgamento(mocker):
    """``cjsg_download`` direto: ``data_inicio`` -> ``data_julgamento_inicio`` ->
    ``dt_inicio`` no payload (refs #183)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            page=1,
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
        ))],
    )

    with pytest.warns(DeprecationWarning) as warning_list:
        result = jus.scraper("tjrn").cjsg_download(
            "dano moral",
            paginas=1,
            data_inicio="2024-01-01",
            data_fim="2024-03-31",
        )

    assert isinstance(result, list)
    messages = [str(w.message) for w in warning_list]
    assert any("data_inicio" in m and "deprecado" in m for m in messages)
    assert any("data_fim" in m and "deprecado" in m for m in messages)


@responses.activate
def test_cjsg_data_julgamento_aceita_formato_brasileiro(mocker):
    """Datas em ``DD/MM/YYYY`` chegam coercidas em ISO ao pipeline.

    Cobre o caminho end-to-end de ``apply_input_pipeline_search`` lendo
    ``BACKEND_DATE_FORMAT='%Y-%m-%d'`` declarado em :class:`InputCJSGTJRN`
    e convertendo via ``coerce_brazilian_date``. Apos a coercao, o
    ``_to_tjrn_date`` ainda reformata o ISO para ``DD-MM-YYYY`` (com tracos)
    porque o backend Elasticsearch so aceita esse formato. O matcher fixa
    o resultado final no body — se a coercao do schema nao acontecer, o
    pipeline tenta passar ``01/01/2024`` para o ``_to_tjrn_date`` e o
    backend recebe um valor invalido (refs #182, #173, #167)."""
    mocker.patch("time.sleep")
    responses.add(
        responses.POST,
        BASE_URL,
        body=load_sample("tjrn", "cjsg/no_results.json"),
        status=200,
        content_type="application/json",
        match=[json_params_matcher(build_cjsg_payload(
            "dano moral",
            page=1,
            dt_inicio="01-01-2024",
            dt_fim="31-03-2024",
        ))],
    )

    df = jus.scraper("tjrn").cjsg(
        "dano moral",
        paginas=1,
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
    )

    assert isinstance(df, pd.DataFrame)
