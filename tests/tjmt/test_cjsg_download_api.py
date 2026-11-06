"""Contratos offline da API atual de jurisprudência do TJMT."""
import json
from typing import Any, cast

import pytest
import requests
from pydantic import ValidationError

from juscraper.core.exceptions import RetryExhaustedError
from juscraper.courts.tjmt.client import TJMTScraper
from juscraper.courts.tjmt.download import (
    MAX_RESULTS,
    PRODUCTION_API_URL,
    TJMTConfigError,
    TJMTResponseError,
    cjsg_download,
)

PORTAL_URL = "https://jurisprudencia.tjmt.jus.br/"
MAIN_URL = f"{PORTAL_URL}assets/main.js"
CHUNK_URL = f"{PORTAL_URL}assets/config.js"
TOKEN = "synthetic-token"


class _RequestRecorder:
    def __init__(self, pages: list[object]):
        self.pages = pages
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, method: str, url: str, **kwargs) -> "_Response":
        self.calls.append((method, url, kwargs))
        body: object
        if url == PORTAL_URL:
            body = '<script src="/assets/main.js"></script>'
        elif url == MAIN_URL:
            body = 'import"./config.js";'
        elif url == CHUNK_URL:
            body = f'const cfg={{api_url:"{PRODUCTION_API_URL}",api_hellsgate_token:"{TOKEN}"}};'
        else:
            page = int(kwargs["params"]["indicePagina"])
            body = self.pages[page]
        return _Response(body if isinstance(body, str) else json.dumps(body))


class _Response(requests.Response):
    def __init__(self, text: str):
        super().__init__()
        self._body = text

    @property
    def text(self) -> str:
        return self._body

    def json(self):
        return json.loads(self._body)


class _ConfigRefreshRecorder:
    """Simula respostas HTTP pela sessão, mantendo o retry real do scraper."""

    def __init__(self, session, tokens, api_statuses):
        self.session = session
        self.tokens = iter(tokens)
        self.api_statuses = iter(api_statuses)
        self.discovery_count = 0
        self.discovery_tokens = []
        self.api_tokens = []
        self.api_statuses_seen = []

    def __call__(self, _method, url, **_kwargs):
        if url == "https://jurisprudencia.tjmt.jus.br/":
            self.discovery_count += 1
            self.discovery_tokens.append(self.session.headers.get("token"))
            body = '<script src="/assets/main.js"></script>'
            status = 200
        elif url.endswith("/assets/main.js"):
            self.discovery_tokens.append(self.session.headers.get("token"))
            body = 'import"./config.js";'
            status = 200
        elif url.endswith("/assets/config.js"):
            self.discovery_tokens.append(self.session.headers.get("token"))
            token = next(self.tokens)
            body = (
                f'const cfg={{api_url:"{PRODUCTION_API_URL}",'
                f'api_hellsgate_token:"{token}"}};'
            )
            status = 200
        else:
            status = next(self.api_statuses)
            self.api_tokens.append(self.session.headers.get("token"))
            self.api_statuses_seen.append(status)
            body = json.dumps(_page([], acordaos=0))

        response = _Response(body)
        response.status_code = status
        response.url = url
        return response


def _page(resultados, *, acordaos=0, decisoes=0, success=True, error_message=None):
    return {
        "value": {
            "resultados": resultados,
            "countAcordaoDocumento": acordaos,
            "countDecisaoMonocratica": decisoes,
        },
        "errorMessage": error_message,
        "success": success,
    }


def test_downloads_acordaos_with_zero_based_pagination_and_headers(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([{"tipo": "Acordao"}], acordaos=11),
        _page([{"tipo": "Acordao"}], acordaos=11),
    ])
    session = requests.Session()

    pages = cjsg_download(
        "dano moral",
        paginas=None,
        quantidade_por_pagina=10,
        request_fn=request,
        session=session,
    )

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert api_calls[0][1] == f"{PRODUCTION_API_URL}/consulta"
    assert api_calls[0][2]["params"] == {
        "indicePagina": 0,
        "quantidadePagina": 10,
        "tipoConsulta": "1",
        "termoDeBusca": "dano moral",
        "tipoBusca": "1",
        "OrdenarPor": "Relevancia",
        "Decrescente": "true",
        "thesaurus": "false",
        "exibirArquivados": "true",
    }
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [0, 1]
    assert all(call[2]["expect_json"] is True for call in api_calls)
    assert api_calls[0][2]["params"]["tipoConsulta"] == "1"
    assert api_calls[0][2]["params"]["termoDeBusca"] == "dano moral"
    assert session.headers["token"] == TOKEN
    assert len(pages) == 2


def test_explicit_non_consecutive_pages_are_converted_to_zero_based(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([], acordaos=30),
        _page([], acordaos=30),
        _page([], acordaos=30),
    ])

    cjsg_download(
        "dano moral",
        paginas=[1, 3],
        request_fn=request,
        session=requests.Session(),
    )

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [0, 2]


def test_integer_pages_downloads_from_first_page_through_requested_page(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([], acordaos=30),
        _page([], acordaos=30),
        _page([], acordaos=30),
    ])

    cjsg_download(
        "dano moral",
        paginas=3,
        request_fn=request,
        session=requests.Session(),
    )

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [0, 1, 2]


def test_single_explicit_page_does_not_expand_integer_page(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=30) for _ in range(3)])

    cjsg_download(
        "dano moral",
        paginas=[3],
        request_fn=request,
        session=requests.Session(),
    )

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [2]


def test_exact_multiple_of_page_size_does_not_fetch_extra_page(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([], acordaos=20),
        _page([], acordaos=20),
    ])

    cjsg_download(
        "dano moral",
        paginas=None,
        quantidade_por_pagina=10,
        request_fn=request,
        session=requests.Session(),
    )

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert len(api_calls) == 2
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [0, 1]


@pytest.mark.parametrize(
    ("kwargs", "exception", "message"),
    [
        ({"quantidade_por_pagina": 0}, ValueError, "tamanho_pagina deve ser maior que zero"),
        ({"quantidade_por_pagina": -1}, ValueError, "tamanho_pagina deve ser maior que zero"),
        ({"quantidade_por_pagina": 1.5}, TypeError, "tamanho_pagina deve ser um inteiro"),
        ({"quantidade_por_pagina": True}, TypeError, "tamanho_pagina deve ser um inteiro"),
        ({"paginas": 0}, ValueError, "paginas"),
        ({"paginas": -1}, ValueError, "paginas"),
        ({"paginas": [0]}, ValueError, "paginas"),
        ({"paginas": [-1]}, ValueError, "paginas"),
        ({"tipo_consulta": "Outro"}, ValueError, "Tipo de consulta"),
    ],
)
def test_rejects_invalid_pagination_and_type_before_network(kwargs, exception, message):
    with pytest.raises(exception, match=message):
        cjsg_download(
            "dano moral",
            request_fn=_NoNetwork(),
            session=requests.Session(),
            **kwargs,
        )


def test_downloads_decisoes_with_tipo_consulta_2_and_specific_count(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([{"tipo": "DecisaoMonocratica"}], acordaos=99, decisoes=1),
    ])

    pages = cjsg_download(
        "dano moral",
        paginas=None,
        tipo_consulta="DecisaoMonocratica",
        quantidade_por_pagina=10,
        request_fn=request,
        session=requests.Session(),
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    assert api_call[2]["params"]["tipoConsulta"] == "2"
    assert len(pages) == 1


def test_explicit_pages_are_one_based_and_empty_results_are_valid(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=0)])

    pages = cjsg_download(
        "termo inexistente",
        paginas=range(1, 2),
        request_fn=request,
        session=requests.Session(),
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    assert api_call[2]["params"]["indicePagina"] == 0
    assert pages[0]["value"]["resultados"] == []


@pytest.mark.parametrize(
    "response",
    [
        {"success": False, "errorMessage": "erro", "value": None},
        # Isolado: envelope válido em tudo, menos em success.
        {"success": False, "errorMessage": None},
        {"success": True, "errorMessage": "erro", "value": {"resultados": []}},
        {"success": True, "errorMessage": None, "value": {}},
        {"success": True, "errorMessage": None, "value": {"resultados": "não é lista"}},
    ],
)
def test_rejects_invalid_api_envelopes(response):
    request = _RequestRecorder([{**_page([], acordaos=0), **response}])

    with pytest.raises(TJMTResponseError):
        cjsg_download(
            "dano moral",
            paginas=range(1, 2),
            request_fn=request,
            session=requests.Session(),
        )


def test_rejects_invalid_json_response():
    request = _RequestRecorder(["não é JSON"])

    with pytest.raises(TJMTResponseError, match="JSON válido"):
        cjsg_download(
            "dano moral",
            paginas=range(1, 2),
            request_fn=request,
            session=requests.Session(),
        )


class _NoNetwork:
    def __call__(self, *_args, **_kwargs):
        raise AssertionError("não deveria haver requisição de rede")


def test_builds_normalized_filters_and_inclusive_publication_interval(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=0)])

    cjsg_download(
        "dano moral",
        paginas=range(1, 2),
        relator="  João   D'Ávila-Silva ",
        orgao_julgador=" Câmara   Cível ",
        tipo_processo="Cível",
        data_publicacao_inicio="19/07/2024",
        data_publicacao_fim="19/07/2024",
        request_fn=request,
        session=requests.Session(),
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    assert api_call[2]["params"] == {
        "indicePagina": 0,
        "quantidadePagina": 10,
        "tipoConsulta": "1",
        "termoDeBusca": "dano moral",
        "tipoBusca": "1",
        "OrdenarPor": "Relevancia",
        "Decrescente": "true",
        "thesaurus": "false",
        "exibirArquivados": "true",
        "periodoDataDe": "2024-07-19",
        "periodoDataAte": "2024-07-19T23:59:59",
        "fqRelator": "JOAO D'AVILA-SILVA",
        "fqOrgaoJulgador": "CAMARA CIVEL",
        "tipoProcesso": "2",
    }


def test_public_download_propagates_publication_date_and_filters(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=0)])
    scraper = TJMTScraper()
    mocker.patch.object(scraper, "_request_with_retry", side_effect=request)

    scraper.cjsg_download(
        "dano moral",
        paginas=1,
        relator="João da Silva",
        orgao_julgador="Primeira Câmara",
        tipo_processo="Criminal",
        data_publicacao_inicio="2024-07-19",
        data_publicacao_fim="2024-07-19",
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    params = api_call[2]["params"]
    assert params["fqRelator"] == "JOAO DA SILVA"
    assert params["fqOrgaoJulgador"] == "PRIMEIRA CAMARA"
    assert params["tipoProcesso"] == "1"
    assert params["periodoDataDe"] == "2024-07-19"
    assert params["periodoDataAte"] == "2024-07-19T23:59:59"


def test_reuses_api_config_across_downloads_on_same_scraper(mocker):
    mocker.patch("time.sleep")
    scraper = TJMTScraper()
    request = _ConfigRefreshRecorder(scraper.session, ["cached-token", "cached-token"], [200, 200])
    mocker.patch.object(scraper.session, "request", side_effect=request)

    scraper.cjsg_download("primeira busca", paginas=1)
    scraper.cjsg_download("segunda busca", paginas=1)

    assert request.discovery_count == 1
    assert request.api_tokens == ["cached-token", "cached-token"]
    assert request.api_statuses_seen == [200, 200]


@pytest.mark.parametrize("status", [401, 403])
def test_unauthorized_api_response_refreshes_config_and_replays_once(status, mocker):
    mocker.patch("time.sleep")
    scraper = TJMTScraper()
    request = _ConfigRefreshRecorder(
        scraper.session,
        ["stale-token", "renewed-token"],
        [status, 200],
    )
    mocker.patch.object(scraper.session, "request", side_effect=request)

    pages = scraper.cjsg_download("dano moral", paginas=1)

    assert pages[0]["success"] is True
    assert request.discovery_count == 2
    assert request.api_tokens == ["stale-token", "renewed-token"]
    assert request.api_statuses_seen == [status, 200]


@pytest.mark.parametrize("status", [401, 403])
def test_refresh_discovery_does_not_send_stale_token(status, mocker):
    mocker.patch("time.sleep")
    scraper = TJMTScraper()
    request = _ConfigRefreshRecorder(
        scraper.session,
        ["stale-token", "renewed-token"],
        [status, 200],
    )
    mocker.patch.object(scraper.session, "request", side_effect=request)

    scraper.cjsg_download("dano moral", paginas=1)

    assert request.discovery_count == 2
    assert "stale-token" not in request.discovery_tokens
    assert request.api_tokens == ["stale-token", "renewed-token"]


def test_failed_config_refresh_restores_cached_session_token(mocker):
    mocker.patch("time.sleep")
    scraper = TJMTScraper()
    request = _ConfigRefreshRecorder(scraper.session, ["stale-token"], [200, 401])
    mocker.patch.object(scraper.session, "request", side_effect=request)
    scraper.cjsg_download("primeira busca", paginas=1)

    def fail_discovery(_request_fn):
        assert scraper.session.headers.get("token") is None
        raise TJMTConfigError("configuração de teste indisponível")

    mocker.patch(
        "juscraper.courts.tjmt.client._get_api_config",
        side_effect=fail_discovery,
    )

    with pytest.raises(TJMTConfigError, match="indisponível"):
        scraper.cjsg_download("segunda busca", paginas=1)

    assert scraper.session.headers["token"] == "stale-token"


@pytest.mark.parametrize("renewed_status", [401, 403])
def test_repeated_unauthorized_response_propagates_without_refresh_loop(renewed_status, mocker):
    mocker.patch("time.sleep")
    scraper = TJMTScraper()
    api_statuses = [401, 401] if renewed_status == 401 else [401, 403, 403, 403]
    api_tokens = ["stale-token", "renewed-token"]
    if renewed_status == 403:
        api_tokens.extend(["renewed-token", "renewed-token"])
    request = _ConfigRefreshRecorder(
        scraper.session,
        ["stale-token", "renewed-token"],
        api_statuses,
    )
    mocker.patch.object(scraper.session, "request", side_effect=request)

    with pytest.raises((requests.HTTPError, RetryExhaustedError)) as exc_info:
        scraper.cjsg_download("dano moral", paginas=1)

    status = (
        exc_info.value.response.status_code
        if isinstance(exc_info.value, requests.HTTPError)
        else exc_info.value.status_code
    )
    assert status == renewed_status
    assert request.discovery_count == 2
    assert request.api_tokens == api_tokens
    assert request.api_statuses_seen == api_statuses


def test_public_integer_pages_downloads_from_first_page_through_requested_page(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([
        _page([], acordaos=30),
        _page([], acordaos=30),
        _page([], acordaos=30),
    ])
    scraper = TJMTScraper()
    mocker.patch.object(scraper, "_request_with_retry", side_effect=request)

    scraper.cjsg_download("dano moral", paginas=3)

    api_calls = [call for call in request.calls if call[1].endswith("/consulta")]
    assert [call[2]["params"]["indicePagina"] for call in api_calls] == [0, 1, 2]


@pytest.mark.parametrize("filter_name", ["relator", "orgao_julgador"])
def test_public_rejects_numeric_filter_ids_before_network(filter_name, mocker):
    request = _NoNetwork()
    scraper = TJMTScraper()
    mocker.patch.object(scraper, "_request_with_retry", side_effect=request)

    with pytest.raises(ValidationError):
        cast(Any, scraper.cjsg_download)("dano moral", paginas=1, **{filter_name: 123})


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2024-07-19", None, {"periodoDataDe": "2024-07-19"}),
        (None, "2024-07-19", {"periodoDataAte": "2024-07-19T23:59:59"}),
        (
            "19/07/2024",
            "20/07/2024",
            {"periodoDataDe": "2024-07-19", "periodoDataAte": "2024-07-20T23:59:59"},
        ),
    ],
)
def test_publication_date_bounds_are_optional_and_inclusive(start, end, expected, mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=0)])

    cjsg_download(
        "dano moral",
        paginas=range(1, 2),
        data_publicacao_inicio=start,
        data_publicacao_fim=end,
        request_fn=request,
        session=requests.Session(),
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    params = api_call[2]["params"]
    assert {key: params[key] for key in expected} == expected


@pytest.mark.parametrize(
    ("tipo_processo", "expected"),
    [("Criminal", "1"), ("Civel", "2"), ("Cível", "2")],
)
def test_maps_tipo_processo(tipo_processo, expected, mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=0)])

    cjsg_download(
        "dano moral",
        paginas=range(1, 2),
        tipo_processo=tipo_processo,
        request_fn=request,
        session=requests.Session(),
    )

    api_call = next(call for call in request.calls if call[1].endswith("/consulta"))
    assert api_call[2]["params"]["tipoProcesso"] == expected


@pytest.mark.parametrize(
    ("filter_name", "value", "exception"),
    [
        ("relator", 123, TypeError),
        ("relator", "123", ValueError),
        ("orgao_julgador", 123, TypeError),
        ("orgao_julgador", "123", ValueError),
        ("tipo_processo", "942", ValueError),
        ("tipo_processo", "Cível Criminal", ValueError),
        ("data_publicacao_inicio", "2024-99-99", ValueError),
    ],
)
def test_rejects_invalid_supported_filters_before_network(filter_name, value, exception):
    with pytest.raises(exception):
        cjsg_download(
            "dano moral",
            paginas=range(1, 2),
            request_fn=_NoNetwork(),
            session=requests.Session(),
            **{filter_name: value},
        )


def test_accepts_empty_filter_values():
    request = _RequestRecorder([_page([], acordaos=0)])

    pages = cjsg_download(
        "dano moral",
        paginas=range(1, 2),
        relator="",
        orgao_julgador="",
        tipo_processo="",
        request_fn=request,
        session=requests.Session(),
    )

    assert pages[0]["value"]["resultados"] == []


@pytest.mark.parametrize("count", [True, False])
def test_rejects_boolean_count(count):
    request = _RequestRecorder([_page([], acordaos=count)])

    with pytest.raises(TJMTResponseError, match="countAcordaoDocumento válido"):
        cjsg_download(
            "dano moral",
            paginas=range(1, 2),
            request_fn=request,
            session=requests.Session(),
        )


def _api_calls(request: _RequestRecorder) -> list[tuple[str, str, dict]]:
    return [call for call in request.calls if call[1].endswith("/consulta")]


def test_paginas_none_para_no_teto_de_resultados_e_avisa(mocker):
    """Com mais de 10.000 resultados, baixa só as páginas que a API responde e avisa."""
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=176269)] * 100)

    with pytest.warns(UserWarning, match=r"176269 resultados.*10000.*os 10000 primeiros"):
        pages = cjsg_download(
            "dano moral",
            paginas=None,
            quantidade_por_pagina=100,
            request_fn=request,
            session=requests.Session(),
        )

    indices = [call[2]["params"]["indicePagina"] for call in _api_calls(request)]
    assert indices == list(range(100))
    assert len(pages) == 100


def test_paginas_none_no_teto_exato_nao_avisa(mocker):
    """Exatamente 10.000 resultados cabem no teto: baixa tudo, sem aviso."""
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=MAX_RESULTS)] * 100)

    pages = cjsg_download(
        "dano moral",
        paginas=None,
        quantidade_por_pagina=100,
        request_fn=request,
        session=requests.Session(),
    )

    assert len(pages) == 100
    assert _api_calls(request)[-1][2]["params"]["indicePagina"] == 99


def test_tamanho_pagina_acima_do_teto_falha_antes_da_rede():
    with pytest.raises(ValueError, match="tamanho_pagina deve ser no máximo 10000"):
        cjsg_download(
            "dano moral",
            paginas=1,
            quantidade_por_pagina=MAX_RESULTS + 1,
            request_fn=_NoNetwork(),
            session=requests.Session(),
        )


@pytest.mark.parametrize(
    ("tamanho", "paginas", "ultima"),
    [(10, [1001], 1000), (100, range(100, 102), 100), (3000, 4, 3)],
)
def test_pagina_alem_do_teto_falha_antes_da_rede(tamanho, paginas, ultima):
    with pytest.raises(ValueError, match=rf"última página alcançável é a {ultima}\b"):
        cjsg_download(
            "dano moral",
            paginas=paginas,
            quantidade_por_pagina=tamanho,
            request_fn=_NoNetwork(),
            session=requests.Session(),
        )


def test_ultima_pagina_dentro_do_teto_e_baixada(mocker):
    mocker.patch("time.sleep")
    request = _RequestRecorder([_page([], acordaos=176269)] * 1000)

    cjsg_download(
        "dano moral",
        paginas=[1000],
        quantidade_por_pagina=10,
        request_fn=request,
        session=requests.Session(),
    )

    assert [call[2]["params"]["indicePagina"] for call in _api_calls(request)] == [999]


@pytest.mark.parametrize(
    "kwargs",
    [{"tamanho_pagina": MAX_RESULTS + 1}, {"paginas": [1001]}],
)
def test_publico_rejeita_paginacao_alem_do_teto_antes_da_rede(kwargs, mocker):
    scraper = TJMTScraper()
    request = mocker.patch.object(scraper, "_request_with_retry", side_effect=_NoNetwork())

    with pytest.raises(ValueError, match="10000"):
        scraper.cjsg("dano moral", **{"paginas": 1, **kwargs})

    request.assert_not_called()
