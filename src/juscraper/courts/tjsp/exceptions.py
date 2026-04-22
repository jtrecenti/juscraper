"""TJSP-specific exceptions."""


class QueryTooLongError(ValueError):
    """Raised when a search query exceeds the TJSP backend maximum length (120 chars)."""


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
