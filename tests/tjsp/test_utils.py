"""
Test utilities for TJSP tests.
"""
import os
from pathlib import Path
from unittest.mock import Mock
import requests


def get_test_samples_dir():
    """Get the path to the test samples directory."""
    test_dir = Path(__file__).parent
    samples_dir = test_dir / "samples"
    return samples_dir


def load_sample_html(filename: str) -> str:
    """
    Load a sample HTML file from the samples directory.
    
    Args:
        filename: Name of the HTML file to load
        
    Returns:
        Contents of the HTML file as a string
        
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    samples_dir = get_test_samples_dir()
    file_path = samples_dir / filename
    
    if not file_path.exists():
        raise FileNotFoundError(f"Sample HTML file not found: {file_path}")
    
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def create_mock_response(html_content: str, status_code: int = 200) -> Mock:
    """
    Create a mock requests.Response object with the given HTML content.
    
    Args:
        html_content: HTML content to return
        status_code: HTTP status code (default: 200)
        
    Returns:
        Mock Response object
    """
    mock_response = Mock(spec=requests.Response)
    mock_response.text = html_content
    mock_response.content = html_content.encode('utf-8')
    mock_response.status_code = status_code
    mock_response.raise_for_status = Mock()
    return mock_response


def create_mock_session_with_responses(responses: dict[str, Mock]) -> Mock:
    """
    Create a mock requests.Session that returns predefined responses.
    
    Args:
        responses: Dictionary mapping URLs or URL patterns to Mock Response objects
        
    Returns:
        Mock Session object
    """
    mock_session = Mock(spec=requests.Session)
    
    def get_side_effect(url, **kwargs):
        # Try exact match first
        if url in responses:
            return responses[url]
        # Try pattern match
        for pattern, response in responses.items():
            if pattern in url:
                return response
        # Default response
        default_response = create_mock_response("", status_code=404)
        return default_response
    
    mock_session.get = Mock(side_effect=get_side_effect)
    mock_session.post = Mock(side_effect=get_side_effect)
    mock_session.cookies = Mock()
    return mock_session

