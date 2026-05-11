"""Shared helpers for juscraper tests.

Centralizes fixture loading and ``responses`` matchers. Used by parser tests
(direct call), contract tests (via ``responses.add(body=load_sample(...))``)
and granular tests.

Examples
--------
>>> from tests._helpers import load_sample
>>> html = load_sample("tjsp", "cjsg/results_normal.html")
"""
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

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


def urlencoded_body_subset_matcher(expected: dict[str, str]):
    """``responses`` matcher that checks only a subset of urlencoded body fields.

    ``responses.matchers.urlencoded_params_matcher`` requires the full body;
    use this when the scraper sends hidden/dynamic fields (CSRF tokens,
    ViewState, crypto tokens) that the contract should not pin down.
    """
    def matcher(request):
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parsed = {k: v[0] if v else "" for k, v in parse_qs(body, keep_blank_values=True).items()}
        missing = {
            k: (expected[k], parsed.get(k))
            for k in expected
            if parsed.get(k) != expected[k]
        }
        if missing:
            return False, f"body fields mismatch: {missing}"
        return True, ""
    return matcher


def assert_unknown_kwarg_raises(
    method: Callable,
    kwarg: str,
    *args,
    valor: str = "x",
    **extra_kwargs,
) -> None:
    """Confirma que ``kwarg`` dispara ``TypeError`` canonico no endpoint.

    Centraliza o regex que da match na mensagem de
    :func:`juscraper.utils.params.raise_on_extra_kwargs`. Mudancas no
    formato da mensagem (aspas, prefixo, sufixo de close-match) ficam
    em uma linha so, em vez de espalhadas em 30+ tribunais.

    Cobre dois cenarios — mecanicamente identicos, ambos sao
    ``extra_forbidden`` puro do pydantic:

    - **Filtros de data nao suportados pelo backend** (issue #186):
      tribunais que so aceitam um dos intervalos
      (``data_julgamento_*`` xor ``data_publicacao_*``) rejeitam o
      oposto via ``extra="forbid"`` do schema.
    - **Kwargs desconhecidos genericos** (issue #84): typos ou
      parametros inventados (ex.: ``parametro_bobo``) sao rejeitados
      pelo mesmo mecanismo.

    Args:
        method (callable): Bound method publico do scraper (e.g.,
            ``jus.scraper("tjmt").cjsg``).
        kwarg (str): Nome do kwarg que deve ser rejeitado (e.g.,
            ``"data_publicacao_inicio"`` para datas, ``"parametro_bobo"``
            para typos genericos).
        *args: Argumentos posicionais propagados para ``method``
            (tipicamente ``"pesquisa"``).
        valor (str): Valor passado em ``kwarg``. Cosmetico — o
            ``TypeError`` e emitido pelo pydantic *antes* de qualquer
            validacao de formato, entao qualquer string serve. Default
            ``"x"``.
        **extra_kwargs: Kwargs extras propagados para ``method`` — util
            para cenarios que precisam de filtros adicionais (ex.: TJSP
            auto_chunk exige uma janela longa de ``data_julgamento_*``
            para acionar o sniff; eSAJ exige ``paginas=1``).
    """
    pattern = rf"got unexpected keyword argument\(s\): '{re.escape(kwarg)}'"
    with pytest.raises(TypeError, match=pattern):
        method(*args, **{kwarg: valor, **extra_kwargs})


def query_param_subset_matcher(expected: dict[str, str]):
    """``responses`` matcher that checks only a subset of query-string params."""
    def matcher(request):
        qs = parse_qs(urlparse(request.url).query, keep_blank_values=True)
        flat = {k: v[0] if v else "" for k, v in qs.items()}
        missing = {
            k: (expected[k], flat.get(k))
            for k in expected
            if flat.get(k) != expected[k]
        }
        if missing:
            return False, f"query params mismatch: {missing}"
        return True, ""
    return matcher
