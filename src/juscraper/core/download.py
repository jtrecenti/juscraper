"""Funções auxiliares de download (gravação em disco, etc.)."""
from __future__ import annotations

import contextlib
from pathlib import Path


def gravar_arquivo(conteudo: bytes, destino: Path) -> Path:
    """Grava ``conteudo`` em ``destino`` por arquivo temporário renomeado.

    Um erro no meio (disco cheio, sem permissão) não deixa arquivo truncado
    nem apaga o que já estava em ``destino``; o ``OSError`` original sobe.
    Cria as pastas de ``destino`` que faltam.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(".tmp")
    try:
        temporario.write_bytes(conteudo)
        temporario.replace(destino)
    except OSError:
        with contextlib.suppress(OSError):
            temporario.unlink(missing_ok=True)
        raise
    return destino
