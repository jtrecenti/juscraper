"""Módulo de utilitários do juscraper. Contém funções auxiliares diversas."""

import re

_SAFE_PATH_COMPONENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def safe_path_component(value, *, field: str = "identificador") -> str:
    r"""Valida que ``value`` é seguro como um único componente de path.

    Identificadores vindos de respostas de tribunais (``cdProcesso``,
    ``cdAcordao``, ``processo.codigo``) são tratados como não confiáveis:
    um valor com separador de path (``/``, ``\\``), segmento ``..`` ou
    vazio nunca é legítimo — significa resposta maliciosa, MITM ou bug
    upstream — e deve falhar alto em vez de gravar fora do diretório de
    download (path traversal). Refs #269.

    Args:
        value: identificador bruto (str ou coercível para str).
        field: nome do campo, usado na mensagem de erro.

    Returns:
        O ``value`` como ``str`` quando seguro.

    Raises:
        ValueError: quando ``value`` não casa ``^[A-Za-z0-9._-]+$`` ou é
            ``"."`` / ``".."``.
    """
    s = str(value)
    if not _SAFE_PATH_COMPONENT_RE.match(s) or s in (".", ".."):
        raise ValueError(
            f"{field} inválido para uso em path: {value!r}. "
            "Esperado apenas caracteres alfanuméricos, '.', '-' e '_'."
        )
    return s


def sanitize_filename(filename: str) -> str:
    """Remove ou substitui caracteres de uma string que não são adequados para nomes de arquivo.

    Permite letras, números, espaços, hífens, underscores e pontos. Substitui sequências
    de caracteres inválidos por um único underscore. Remove underscores no início ou fim
    do nome.
    """
    # Remove caracteres inválidos, substituindo por underscore
    # Permite letras (incluindo acentuadas), números, espaços, hífens, underscores, pontos.
    # Caracteres como / \ : * ? " < > | são problemáticos
    filename = re.sub(r'[^a-zA-Z0-9_\-. ]', '_', filename)
    # Substitui múltiplos underscores (ou espaços que viraram underscores) por um único underscore
    filename = re.sub(r'_+', '_', filename)
    # Remove underscores no início ou fim do nome
    filename = filename.strip('_')
    if not filename:  # Se o nome do arquivo ficar vazio após a sanitização
        filename = "default_filename"
    return filename
