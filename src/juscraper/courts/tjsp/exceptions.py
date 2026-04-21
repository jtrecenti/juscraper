"""Canonical TJSP-specific exceptions."""


class QueryTooLongError(ValueError):
    """Raised when a search query exceeds the TJSP backend maximum length (120 chars).

    Historically lived in ``tjsp/cjsg_download.py`` and ``tjsp/cjpg_download.py``.
    Those modules now re-export from here for backwards compatibility with
    legacy unit tests (``tests/tjsp/test_query_validation.py``,
    ``tests/tjsp/test_search_limit.py``) and the offline contract tests.
    """


_TJSP_PESQUISA_MAX_CHARS = 120


def validate_pesquisa_length(pesquisa: str | None, *, endpoint: str) -> None:
    """Raise ``QueryTooLongError`` when ``pesquisa`` exceeds 120 characters."""
    if pesquisa is not None and len(pesquisa) > _TJSP_PESQUISA_MAX_CHARS:
        raise QueryTooLongError(
            f"O campo 'pesquisa' do {endpoint} do TJSP aceita no máximo "
            f"{_TJSP_PESQUISA_MAX_CHARS} caracteres "
            f"(recebido: {len(pesquisa)} caracteres). "
            "Reduza a busca ou divida em consultas menores."
        )
