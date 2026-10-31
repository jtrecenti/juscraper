"""Testes da descoberta dinâmica da configuração da API do TJMT."""
from urllib.parse import urljoin

import pytest
import requests

from juscraper.courts.tjmt.download import (
    MAX_CONFIG_RESOURCES,
    PORTAL_URL,
    TJMTConfigError,
    _extract_api_config,
    _get_api_config,
    _validate_api_config,
)

API_URL = "https://hellsgate.tjmt.jus.br/jurisprudencia"
TOKEN = "synthetic-token-never-log"


def _response(url: str, body: str, status: int = 200) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.headers["Content-Type"] = "text/html"
    response.__dict__["_content"] = body.encode()
    return response


class _Recorder:
    def __init__(self, resources: dict[str, str]):
        self.resources = resources
        self.calls: list[str] = []

    def __call__(self, method: str, url: str, **_kwargs) -> requests.Response:
        assert method == "GET"
        self.calls.append(url)
        if url not in self.resources:
            raise AssertionError(f"recurso não mockado: {url}")
        return _response(url, self.resources[url])


def _request_fn(resources: dict[str, str]) -> _Recorder:
    return _Recorder(resources)


def test_discovery_finds_config_in_imported_chunk():
    request = _request_fn({
        PORTAL_URL: '<script src="/assets/main-new-name.js"></script>',
        urljoin(PORTAL_URL, "assets/main-new-name.js"): 'import "./chunk-new-name.js";',
        urljoin(PORTAL_URL, "assets/chunk-new-name.js"):
            f'const cfg={{api_url:"{API_URL}",api_hellsgate_token:"{TOKEN}"}};',
    })

    assert _get_api_config(request) == {"api_url": API_URL, "token": TOKEN}
    assert request.calls == [
        PORTAL_URL,
        urljoin(PORTAL_URL, "assets/main-new-name.js"),
        urljoin(PORTAL_URL, "assets/chunk-new-name.js"),
    ]


def test_discovery_finds_config_in_minified_from_import():
    chunk_url = urljoin(PORTAL_URL, "assets/chunk-minified.js")
    request = _request_fn({
        PORTAL_URL: '<script src="/assets/main-new-name.js"></script>',
        urljoin(PORTAL_URL, "assets/main-new-name.js"):
            'import{$d as ec}from"./chunk-minified.js";',
        chunk_url: f'const cfg={{api_url:"{API_URL}",api_hellsgate_token:"{TOKEN}"}};',
    })

    assert _get_api_config(request) == {"api_url": API_URL, "token": TOKEN}
    assert request.calls == [PORTAL_URL, urljoin(PORTAL_URL, "assets/main-new-name.js"), chunk_url]


@pytest.mark.parametrize(
    "preload",
    [
        '<link rel="modulepreload" href="/assets/preloaded-config.js">',
        '<link href="/assets/preloaded-config.js" rel="modulepreload">',
    ],
)
def test_discovery_finds_config_in_modulepreload_chunk(preload):
    chunk_url = urljoin(PORTAL_URL, "assets/preloaded-config.js")
    request = _request_fn({
        PORTAL_URL: preload,
        chunk_url: f'const cfg={{api_url:"{API_URL}",api_hellsgate_token:"{TOKEN}"}};',
    })

    assert _get_api_config(request) == {"api_url": API_URL, "token": TOKEN}


def test_extraction_accepts_nested_object_and_quoted_properties():
    script = f"""
    const cfg = {{
        production: !0,
        'api_url': '{API_URL}',
        "api_hellsgate_token": '{TOKEN}',
        recaptcha: {{ url_api: 'https://captcha.test', site_key: 'synthetic', sistema_id: 2353 }}
    }};
    """

    assert _extract_api_config(script) == {
        "api_url": API_URL,
        "api_hellsgate_token": TOKEN,
    }


def test_extraction_does_not_combine_separate_objects():
    script = f"""
    const url_config = {{ api_url: '{API_URL}' }};
    const token_config = {{ api_hellsgate_token: '{TOKEN}' }};
    """

    assert _extract_api_config(script) is None


def test_extraction_ignores_comments_with_braces():
    script = f"""
    const cfg = {{
        // comentário com {{ uma chave falsa e }} outra
        /* comentário {{ api_url: 'fake' }} */
        api_url: '{API_URL}',
        api_hellsgate_token: '{TOKEN}'
    }};
    """

    assert _extract_api_config(script) == {
        "api_url": API_URL,
        "api_hellsgate_token": TOKEN,
    }


def test_extraction_rejects_partial_property_names():
    script = f"""
    const cfg = {{
        some_api_url: '{API_URL}',
        some_api_hellsgate_token: '{TOKEN}'
    }};
    """

    assert _extract_api_config(script) is None


def test_discovery_handles_repeated_and_circular_imports():
    request = _request_fn({
        PORTAL_URL: '<script src="/a.js"></script><script src="/a.js"></script>',
        urljoin(PORTAL_URL, "a.js"): 'import "./b.js";',
        urljoin(PORTAL_URL, "b.js"):
            f'import "./a.js"; const c={{api_url:"{API_URL}",api_hellsgate_token:"{TOKEN}"}};',
    })

    assert _get_api_config(request)["api_url"] == API_URL
    assert request.calls.count(urljoin(PORTAL_URL, "a.js")) == 1


def test_discovery_rejects_missing_or_malformed_config():
    request = _request_fn({
        PORTAL_URL: '<script src="/main.js"></script>',
        urljoin(PORTAL_URL, "main.js"): 'const cfg={api_url:"not-complete"};',
    })

    with pytest.raises(TJMTConfigError, match="não encontrada") as exc:
        _get_api_config(request)
    assert TOKEN not in str(exc.value)


def test_discovery_rejects_unexpected_api_url_without_leaking_token():
    secret = "synthetic-secret-that-must-not-appear"
    request = _request_fn({
        PORTAL_URL: '<script src="/main.js"></script>',
        urljoin(PORTAL_URL, "main.js"):
            f'const cfg={{api_url:"https://example.test/api",api_hellsgate_token:"{secret}"}};',
    })

    with pytest.raises(TJMTConfigError, match="endpoint de produção") as exc:
        _get_api_config(request)
    assert secret not in str(exc.value)


def test_discovery_rejects_unexpected_api_path():
    request = _request_fn({
        PORTAL_URL: '<script src="/main.js"></script>',
        urljoin(PORTAL_URL, "main.js"):
            f'const cfg={{api_url:"{API_URL}/api",api_hellsgate_token:"{TOKEN}"}};',
    })

    with pytest.raises(TJMTConfigError, match="endpoint de produção"):
        _get_api_config(request)


@pytest.mark.parametrize("url", [
    "https://hellsgate.tjmt.jus.br/jurisprudencia?versao=1",
    "https://hellsgate.tjmt.jus.br/jurisprudencia?",
    "https://hellsgate.tjmt.jus.br/jurisprudencia#fragmento",
    "https://hellsgate.tjmt.jus.br/jurisprudencia#",
    "https://user:pass@hellsgate.tjmt.jus.br/jurisprudencia",
    "https://hellsgate.tjmt.jus.br:8443/jurisprudencia",
    "https://hellsgate.tjmt.jus.br:/jurisprudencia",
])
def test_validation_rejects_unsafe_production_url_variants(url):
    with pytest.raises(TJMTConfigError, match="endpoint de produção"):
        _validate_api_config({"api_url": url, "api_hellsgate_token": TOKEN})


def test_discovery_enforces_resource_limit():
    resources = {PORTAL_URL: '<script src="/0.js"></script>'}
    for index in range(MAX_CONFIG_RESOURCES):
        next_script = f'import "./{index + 1}.js";' if index + 1 < MAX_CONFIG_RESOURCES else ""
        resources[urljoin(PORTAL_URL, f"{index}.js")] = next_script
    request = _request_fn(resources)

    with pytest.raises(TJMTConfigError, match="Limite de recursos"):
        _get_api_config(request)
    assert len(request.calls) == MAX_CONFIG_RESOURCES + 1
