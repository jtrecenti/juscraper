"""
Test utilities for TJSP tests.

Sample loading lives in ``tests._helpers`` (``load_sample``/``load_sample_bytes``).
This module keeps only the mock helpers that have no equivalent there.
"""
from unittest.mock import Mock

import requests


def create_mock_response(html_content: str, status_code: int = 200) -> Mock:
    """Return a ``Mock`` that quacks like a ``requests.Response``.

    Args:
        html_content: HTML body the mock should return via ``.text``/``.content``.
        status_code: HTTP status code (default: 200).
    """
    mock_response = Mock(spec=requests.Response)
    mock_response.text = html_content
    mock_response.content = html_content.encode('utf-8')
    mock_response.status_code = status_code
    mock_response.raise_for_status = Mock()
    return mock_response


def create_mock_session_with_responses(responses: dict[str, Mock]) -> Mock:
    """Return a ``Mock`` session that dispatches by URL match.

    Args:
        responses: Dict mapping URL substrings to mocked ``Response`` objects.
            Exact match wins over substring match; absent matches yield 404.
    """
    mock_session = Mock(spec=requests.Session)

    def get_side_effect(url, **kwargs):
        if url in responses:
            return responses[url]
        for pattern, response in responses.items():
            if pattern in url:
                return response
        return create_mock_response("", status_code=404)

    mock_session.get = Mock(side_effect=get_side_effect)
    mock_session.post = Mock(side_effect=get_side_effect)
    mock_session.cookies = Mock()
    return mock_session
