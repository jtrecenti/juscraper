"""Shared helpers for juscraper tests.

Centralizes fixture loading. Used by parser tests (direct call), contract
tests (via ``responses.add(body=load_sample(...))``) and granular tests.

Examples
--------
>>> from tests._helpers import load_sample
>>> html = load_sample("tjsp", "cjsg/results_normal.html")
"""
from pathlib import Path

_SAMPLES_ROOT = Path(__file__).parent


def load_sample(tribunal: str, relative_path: str, *, encoding: str = "utf-8") -> str:
    """Load a sample fixture as string.

    Parameters
    ----------
    tribunal : str
        Court directory under ``tests/`` (e.g., ``"tjsp"``, ``"tjac"``).
    relative_path : str
        Path inside ``tests/<tribunal>/samples/`` (e.g., ``"cjsg/results_normal.html"``).
    encoding : str
        File encoding. Defaults to ``"utf-8"``.

    Returns
    -------
    str
        File contents.

    Raises
    ------
    FileNotFoundError
        If the sample file does not exist.
    """
    path = _SAMPLES_ROOT / tribunal / "samples" / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Sample not found: {path}")
    return path.read_text(encoding=encoding)


def load_sample_bytes(tribunal: str, relative_path: str) -> bytes:
    """Load a sample fixture as raw bytes.

    Use when the parser needs to handle encoding itself (eSAJ HTML
    is served as latin-1, for example).
    """
    path = _SAMPLES_ROOT / tribunal / "samples" / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Sample not found: {path}")
    return path.read_bytes()
