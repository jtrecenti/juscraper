"""Testes de ``juscraper.core.http.HTTPScraper._request_with_retry``.

Inclui os casos canônicos da issue #185 (validação de ``session=`` na fronteira).
"""
from __future__ import annotations

import pytest
import requests
import responses

from juscraper.core.exceptions import RetryExhaustedError
from juscraper.core.http import HTTPScraper

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
