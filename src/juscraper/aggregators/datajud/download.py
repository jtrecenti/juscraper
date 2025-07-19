"""
Functions for downloading specific data from the Datajud API.
"""
from typing import Optional, Dict, Any
import logging
import requests

logger = logging.getLogger(__name__)

def call_datajud_api(
    base_url: str,
    alias: str,
    api_key: str,
    session: requests.Session,
    query_payload: Dict[str, Any],
    verbose: bool = False,
    timeout: int = 60  # seconds
) -> Optional[Dict[str, Any]]:
    """
    Calls the Datajud API for a given alias with a specific query.

    Args:
        base_url (str): The base URL of Datajud API (e.g. https://api-publica.datajud.cnj.jus.br).
        alias (str): The API alias for the specific tribunal/service (e.g. api_publica_tjsp).
        api_key (str): The API key for authorization.
        session (requests.Session): The requests session to use.
        query_payload (Dict[str, Any]): The Elasticsearch query payload.
        verbose (bool): If True, logs more details about the request.
        timeout (int): Request timeout in seconds.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the API as a dictionary, 
                                   or None if the request fails or returns an error.
    """
    api_url = f"{base_url}/{alias}/_search"
    headers = {
        "Authorization": f"APIKey {api_key}",
        "Content-Type": "application/json"
    }

    if verbose:
        logger.info("Calling Datajud API: %s", api_url)
        # Redact key in log for security
        logger.debug(
            "Headers: {'Authorization': 'APIKey [REDACTED]',"
            "'Content-Type': 'application/json'}"
        )
        logger.debug("Payload: %s", query_payload)

    try:
        response = session.post(api_url, json=query_payload, headers=headers, timeout=timeout)
        if verbose:
            logger.debug("Response Status Code: %s", response.status_code)
            # Optionally log more details, but be mindful of verbosity and sensitive data
            # logger.debug(f"Response Headers: {response.headers}")
            # logger.debug(f"Response Content (first 500 chars): {response.text[:500]}")

        response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
        return response.json()

    except requests.exceptions.HTTPError as e:
        logger.error("HTTP Error calling Datajud API (%s): %s", api_url, e)
        if e.response is not None:
            logger.error("Response status: %s", e.response.status_code)
            try:
                logger.error("Response content: %s", e.response.text[:1000])
            except Exception:
                logger.error("Could not retrieve error response content.")
        else:
            logger.error("No response object available in HTTPError.")
        return None
    except requests.exceptions.Timeout:
        logger.error("Timeout calling Datajud API (%s) after %d seconds.", api_url, timeout)
        return None
    except requests.exceptions.RequestException as e:
        logger.error("Request failed for Datajud API (%s): %s", api_url, e)
        return None
    except ValueError as e: # Includes JSONDecodeError if response is not valid JSON
        logger.error("Failed to decode JSON response from Datajud API (%s): %s", api_url, e)
        # Try to log part of the response text if available and decoding failed
        response_text_snippet = 'N/A'
        if 'response' in locals() and hasattr(response, 'text'):
            response_text_snippet = response.text[:500]
        logger.error("Response text (first 500 chars): %s", response_text_snippet)
        return None
    except Exception as e:
        logger.error("An unexpected error occurred calling Datajud API (%s): %s", api_url, e)
        return None
