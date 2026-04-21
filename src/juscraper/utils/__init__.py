"""Módulo de utilitários do juscraper. Contém funções auxiliares diversas."""

import re


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
