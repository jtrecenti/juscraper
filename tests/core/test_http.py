"""Testes de ``juscraper.core.http.HTTPScraper._request_with_retry``.

Inclui os casos canônicos da issue #185 (validação de ``session=`` na fronteira).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pytest
import requests
import responses

from juscraper.core.exceptions import InvalidJSONResponseError, RetryExhaustedError
from juscraper.core.http import DEFAULT_POLICY, RETRYABLE_STATUSES, HTTPScraper, RequestPolicy

URL = "https://example.test/api"


class _Probe(HTTPScraper):
    """Subclasse mínima de HTTPScraper só para instanciar nos testes."""


@pytest.fixture
def probe(mocker):
    mocker.patch("juscraper.core.http.time.sleep")
    return _Probe()


@responses.activate
def test_request_with_retry_200_immediate(probe, mocker):
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    sleep_spy.assert_not_called()


@responses.activate
def test_request_with_retry_429_with_retry_after(probe, mocker):
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=429, headers={"Retry-After": "0.1"})
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    sleep_spy.assert_called_once_with(0.1)


@responses.activate
def test_request_with_retry_5xx_with_backoff(probe, mocker):
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=503)
    responses.add(responses.GET, URL, status=503)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    waits = [c.args[0] for c in sleep_spy.call_args_list]
    assert waits == [2.0, 4.0]


@responses.activate
def test_request_with_retry_exhausted(probe):
    for _ in range(3):
        responses.add(responses.GET, URL, status=503)

    with pytest.raises(RetryExhaustedError) as exc:
        probe._request_with_retry("GET", URL)

    assert exc.value.status_code == 503
    assert exc.value.attempts == 3


def test_request_with_retry_invalid_session_raises_typeerror(probe):
    with pytest.raises(TypeError, match=r"session deve ser requests\.Session, recebido str"):
        probe._request_with_retry("GET", URL, session="oops")


@responses.activate
def test_request_with_retry_session_none_uses_self_session(probe, mocker):
    spy = mocker.spy(probe.session, "request")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe._request_with_retry("GET", URL, session=None)

    assert spy.call_count == 1


@responses.activate
def test_request_with_retry_session_override(probe, mocker):
    self_spy = mocker.spy(probe.session, "request")
    override = requests.Session()
    override_spy = mocker.spy(override, "request")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe._request_with_retry("GET", URL, session=override)

    assert override_spy.call_count == 1
    assert self_spy.call_count == 0


@responses.activate
def test_request_with_retry_retry_after_invalid_falls_back(probe, mocker):
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=503, headers={"Retry-After": "banana"})
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe._request_with_retry("GET", URL)

    sleep_spy.assert_called_once_with(2.0)


@responses.activate
def test_request_with_retry_4xx_no_retry(probe):
    responses.add(responses.GET, URL, status=404)
    responses.add(responses.GET, URL, status=200)

    with pytest.raises(requests.HTTPError):
        probe._request_with_retry("GET", URL)


@responses.activate
def test_request_with_retry_403_with_backoff(probe, mocker):
    """403 e retryable (WAF do TJSP eSAJ, #233) e usa o mesmo backoff de 5xx."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=403)
    responses.add(responses.GET, URL, status=403)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    waits = [c.args[0] for c in sleep_spy.call_args_list]
    assert waits == [2.0, 4.0]


@responses.activate
def test_request_with_retry_403_exhausted(probe, mocker):
    """403 persistente esgota ``max_retries`` em ``RetryExhaustedError`` (nao ``HTTPError``)."""
    mocker.patch("juscraper.core.http.time.sleep")
    for _ in range(3):
        responses.add(responses.GET, URL, status=403)

    with pytest.raises(RetryExhaustedError) as exc:
        probe._request_with_retry("GET", URL)

    assert exc.value.status_code == 403
    assert exc.value.attempts == 3


@responses.activate
def test_request_with_retry_403_with_retry_after(probe, mocker):
    """403 tambem respeita ``Retry-After`` numerico (mesmo branch de 429/5xx)."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=403, headers={"Retry-After": "0.5"})
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    sleep_spy.assert_called_once_with(0.5)


@responses.activate
def test_request_with_retry_max_retries_param(probe, mocker):
    mocker.patch("juscraper.core.http.time.sleep")
    for _ in range(2):
        responses.add(responses.GET, URL, status=503)

    with pytest.raises(RetryExhaustedError) as exc:
        probe._request_with_retry("GET", URL, max_retries=2)

    assert exc.value.attempts == 2


def test_init_sets_user_agent_and_session():
    probe = _Probe()
    assert isinstance(probe.session, requests.Session)
    assert "juscraper" in probe.session.headers.get("User-Agent", "")
    assert probe.sleep_time == 1.0


def test_configure_session_hook_called(mocker):
    spy_calls: list = []

    class _ProbeWithHook(HTTPScraper):
        def _configure_session(self, session):
            spy_calls.append(session)

    instance = _ProbeWithHook()
    assert spy_calls == [instance.session]


@responses.activate
def test_request_with_retry_post_forwards_body(probe):
    """POST encaminha ``json=`` via ``**kwargs`` para ``session.request``."""
    captured: dict = {}

    def _callback(request):
        captured["body"] = request.body
        captured["method"] = request.method
        return (200, {}, '{"ok": true}')

    responses.add_callback(responses.POST, URL, callback=_callback, content_type="application/json")

    resp = probe._request_with_retry("POST", URL, json={"x": 1})

    assert resp.status_code == 200
    assert captured["method"] == "POST"
    assert captured["body"] == b'{"x": 1}'


@responses.activate
def test_request_with_retry_negative_retry_after_clamped(probe, mocker):
    """``Retry-After: -5`` é tolerado (clamp em 0) em vez de explodir em ``time.sleep``."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=503, headers={"Retry-After": "-5"})
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe._request_with_retry("GET", URL)

    sleep_spy.assert_called_once_with(0.0)


def test_request_with_retry_invalid_max_retries(probe):
    with pytest.raises(ValueError, match=r"max_retries deve ser >= 1, recebido 0"):
        probe._request_with_retry("GET", URL, max_retries=0)


@responses.activate
def test_request_with_retry_200_invalid_json_no_retry(probe, mocker):
    """200 com body invalido nao retenta — caller chama ``.json()`` e ``ValueError`` propaga.

    Documenta a mudanca herdada pelo refactor #194: o ``_fetch_page`` antigo
    de TJAP/TJES capturava ``ValueError`` no laco de retry, mas o
    ``_request_with_retry`` so retry-a 429/5xx — entao body invalido em 200
    propaga ``ValueError`` na primeira ocorrencia. Refs #202.
    """
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, body="not-json", status=200, content_type="application/json")

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    sleep_spy.assert_not_called()
    with pytest.raises(ValueError):
        resp.json()


@responses.activate
def test_request_with_retry_expect_json_retries_empty_body(probe, mocker):
    """``expect_json=True`` trata 200 com corpo vazio como transitório e retenta. Refs #275."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, body="", status=200)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL, expect_json=True)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    sleep_spy.assert_called_once_with(2.0)


@responses.activate
def test_request_with_retry_expect_json_exhausted_raises_invalid_json(probe, mocker):
    """Corpo vazio persistente com ``expect_json=True`` levanta ``InvalidJSONResponseError``. Refs #275."""
    mocker.patch("juscraper.core.http.time.sleep")
    for _ in range(3):
        responses.add(responses.GET, URL, body="", status=200)

    with pytest.raises(InvalidJSONResponseError) as exc:
        probe._request_with_retry("GET", URL, expect_json=True)

    assert exc.value.status_code == 200
    assert exc.value.attempts == 3
    assert exc.value.url == URL


@responses.activate
def test_request_with_retry_expect_json_default_off_does_not_retry(probe, mocker):
    """Sem ``expect_json``, 200 com corpo inválido não retenta (default preservado, #202)."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, body="not-json", status=200, content_type="application/json")

    resp = probe._request_with_retry("GET", URL)

    assert resp.status_code == 200
    sleep_spy.assert_not_called()
    with pytest.raises(ValueError):
        resp.json()


class _SentinelError(Exception):
    """Erro de teste levantado pelo callback ``on_response``."""


@responses.activate
def test_request_with_retry_on_response_short_circuits_retry(probe, mocker):
    """Um ``on_response`` que levanta curto-circuita o retry de status retryable.

    403 está em ``RETRYABLE_STATUSES``; sem o callback, seria retentado até
    ``RetryExhaustedError``. Com o callback levantando, a exceção propaga na
    primeira resposta — é como o ``_trf`` transforma o 403 do Akamai em
    ``BotChallengeBlockedError`` sem gastar tentativas num bloqueio session-wide.
    """
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    # Só uma resposta registrada: se houvesse retry, o responses levantaria
    # ConnectionError por falta de mock para a 2a tentativa.
    responses.add(responses.GET, URL, status=403)

    def _raise(resp):
        if resp.status_code == 403:
            raise _SentinelError

    with pytest.raises(_SentinelError):
        probe._request_with_retry("GET", URL, on_response=_raise)

    assert len(responses.calls) == 1
    sleep_spy.assert_not_called()


@responses.activate
def test_request_with_retry_on_response_noop_lets_flow_proceed(probe, mocker):
    """Um ``on_response`` que não levanta deixa o fluxo normal (retry/return) seguir."""
    mocker.patch("juscraper.core.http.time.sleep")
    seen: list[int] = []
    responses.add(responses.GET, URL, status=503)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    resp = probe._request_with_retry("GET", URL, on_response=lambda r: seen.append(r.status_code))

    assert resp.status_code == 200
    # O callback viu as duas respostas (503 transitório, depois 200).
    assert seen == [503, 200]


# --- Política de requisição por perfil -------------------------------------


class _ProbeComPerfis(HTTPScraper):
    """Scraper com perfis declarados, como PDPJ/JusBR farão."""

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "listagem": RequestPolicy(timeout=60),
        "documento": RequestPolicy(
            timeout=30,
            max_retries=4,
            retryable_statuses=frozenset({429, 503}),
            retry_on_timeout=True,
        ),
    }


@pytest.fixture
def probe_perfis(mocker):
    mocker.patch("juscraper.core.http.time.sleep")
    return _ProbeComPerfis()


def test_default_policy_matches_previous_behavior():
    assert RequestPolicy(
        timeout=None,
        max_retries=3,
        base_backoff=2.0,
        retryable_statuses=RETRYABLE_STATUSES,
        retry_on_timeout=False,
        retry_on_connection_error=False,
    ) == DEFAULT_POLICY


def test_politica_merges_only_passed_fields():
    probe = _ProbeComPerfis(politica={"documento": {"timeout": 10}})

    doc = probe._perfis_http["documento"]
    assert doc.timeout == 10
    assert doc.max_retries == 4
    assert doc.retryable_statuses == frozenset({429, 503})
    assert doc.retry_on_timeout is True
    assert probe._perfis_http["listagem"] == _ProbeComPerfis.perfis_http["listagem"]


def test_politica_does_not_mutate_class_profiles():
    _ProbeComPerfis(politica={"documento": {"timeout": 10}})
    assert _ProbeComPerfis.perfis_http["documento"].timeout == 30


def test_politica_coerces_statuses_to_frozenset():
    probe = _ProbeComPerfis(politica={"documento": {"retryable_statuses": [500]}})
    assert probe._perfis_http["documento"].retryable_statuses == frozenset({500})


def test_politica_on_scraper_without_profiles_raises():
    with pytest.raises(ValueError, match="não declara perfis HTTP"):
        _Probe(politica={"documento": {"timeout": 10}})


def test_politica_unknown_profile_raises():
    with pytest.raises(ValueError, match=r"Perfil HTTP desconhecido.*'inexistente'"):
        _ProbeComPerfis(politica={"inexistente": {"timeout": 10}})


def test_politica_unknown_field_raises():
    with pytest.raises(ValueError, match=r"Campo.*desconhecido.*'tempo'"):
        _ProbeComPerfis(politica={"documento": {"tempo": 10}})


def test_politica_invalid_max_retries_raises():
    with pytest.raises(ValueError, match=r"max_retries deve ser >= 1, recebido 0"):
        _ProbeComPerfis(politica={"documento": {"max_retries": 0}})


def test_request_unknown_profile_raises(probe_perfis):
    with pytest.raises(ValueError, match=r"Perfil HTTP desconhecido.*'inexistente'"):
        probe_perfis._request_with_retry("GET", URL, perfil="inexistente")


def test_request_profile_on_scraper_without_profiles_raises(probe):
    with pytest.raises(ValueError, match="Perfil HTTP desconhecido"):
        probe._request_with_retry("GET", URL, perfil="documento")


@responses.activate
def test_profile_timeout_reaches_session_request(probe_perfis, mocker):
    spy = mocker.spy(probe_perfis.session, "request")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe_perfis._request_with_retry("GET", URL, perfil="documento")

    assert spy.call_args.kwargs["timeout"] == 30
    assert "perfil" not in spy.call_args.kwargs


@responses.activate
def test_no_profile_injects_no_timeout(probe_perfis, mocker):
    spy = mocker.spy(probe_perfis.session, "request")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe_perfis._request_with_retry("GET", URL)

    assert "timeout" not in spy.call_args.kwargs


@responses.activate
def test_explicit_timeout_beats_profile(probe_perfis, mocker):
    spy = mocker.spy(probe_perfis.session, "request")
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    probe_perfis._request_with_retry("GET", URL, perfil="documento", timeout=5)

    assert spy.call_args.kwargs["timeout"] == 5


@responses.activate
def test_explicit_max_retries_beats_profile(probe_perfis):
    for _ in range(4):
        responses.add(responses.GET, URL, status=503)

    with pytest.raises(RetryExhaustedError) as exc:
        probe_perfis._request_with_retry("GET", URL, perfil="documento", max_retries=2)

    assert exc.value.attempts == 2


@responses.activate
def test_profile_max_retries_used(probe_perfis):
    for _ in range(4):
        responses.add(responses.GET, URL, status=503)

    with pytest.raises(RetryExhaustedError) as exc:
        probe_perfis._request_with_retry("GET", URL, perfil="documento")

    assert exc.value.attempts == 4


@responses.activate
def test_profile_retryable_statuses_drop_403(probe_perfis, mocker):
    """No perfil que tira o 403 dos retentáveis, ele vira ``HTTPError`` na primeira resposta."""
    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    responses.add(responses.GET, URL, status=403)
    responses.add(responses.GET, URL, json={"ok": True}, status=200)

    with pytest.raises(requests.HTTPError):
        probe_perfis._request_with_retry("GET", URL, perfil="documento")

    assert len(responses.calls) == 1
    sleep_spy.assert_not_called()


@pytest.mark.parametrize(
    ("exc_cls", "perfil"),
    [
        (requests.ReadTimeout, {"retry_on_timeout": True}),
        (requests.ConnectionError, {"retry_on_connection_error": True}),
        (requests.ConnectTimeout, {"retry_on_connection_error": True}),
    ],
)
def test_network_error_retried_when_enabled(mocker, exc_cls, perfil):
    class _P(HTTPScraper):
        perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {"p": RequestPolicy(**perfil)}

    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    probe = _P()
    ok = requests.Response()
    ok.status_code = 200
    mocker.patch.object(probe.session, "request", side_effect=[exc_cls(), exc_cls(), ok])

    resp = probe._request_with_retry("GET", URL, perfil="p")

    assert resp is ok
    assert [c.args[0] for c in sleep_spy.call_args_list] == [2.0, 4.0]


@pytest.mark.parametrize(
    ("exc_cls", "perfil"),
    [
        (requests.ReadTimeout, {"retry_on_connection_error": True}),
        (requests.ConnectionError, {"retry_on_timeout": True}),
        (requests.ConnectTimeout, {"retry_on_timeout": True}),
        (requests.ReadTimeout, None),
        (requests.ConnectionError, None),
    ],
)
def test_network_error_not_retried_when_disabled(mocker, exc_cls, perfil):
    class _P(HTTPScraper):
        perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {"p": RequestPolicy(**perfil)} if perfil else {}

    sleep_spy = mocker.patch("juscraper.core.http.time.sleep")
    probe = _P()
    request = mocker.patch.object(probe.session, "request", side_effect=exc_cls())

    with pytest.raises(exc_cls):
        probe._request_with_retry("GET", URL, perfil="p" if perfil else None)

    assert request.call_count == 1
    sleep_spy.assert_not_called()


def test_network_retry_exhausted_reraises_original(probe_perfis, mocker):
    """Esgotado, relança o próprio timeout (motivo ``timeout``), não ``RetryExhaustedError``."""
    request = mocker.patch.object(probe_perfis.session, "request", side_effect=requests.ReadTimeout())

    with pytest.raises(requests.ReadTimeout):
        probe_perfis._request_with_retry("GET", URL, perfil="documento")

    assert request.call_count == 4


def test_network_and_status_share_max_retries(probe_perfis, mocker):
    """Timeout e status retentável gastam do mesmo ``max_retries``."""
    indisponivel = requests.Response()
    indisponivel.status_code = 503
    request = mocker.patch.object(
        probe_perfis.session, "request",
        side_effect=[requests.ReadTimeout(), indisponivel, requests.ReadTimeout(), indisponivel],
    )

    with pytest.raises(RetryExhaustedError) as exc:
        probe_perfis._request_with_retry("GET", URL, perfil="documento")

    assert exc.value.attempts == 4
    assert request.call_count == 4
