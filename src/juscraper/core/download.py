"""Funções auxiliares de download (gravação em disco, etc.)."""
from __future__ import annotations

import contextlib
from pathlib import Path


class ErroDeGravacaoError(OSError):
    """O ``OSError`` de :func:`gravar_arquivo`, com os mesmos ``errno``, mensagem e arquivo.

    Separa a falha de disco dos outros ``OSError`` de um download (as exceções
    do ``requests`` também herdam dele), para os lotes que a convertem em
    linha com :data:`juscraper.core.failures.MOTIVO_ERRO_DE_GRAVACAO`. O erro
    original fica em ``__cause__``.
    """


def gravar_arquivo(conteudo: bytes, destino: Path) -> Path:
    """Grava ``conteudo`` em ``destino`` por arquivo temporário renomeado.

    Um erro no meio (disco cheio, sem permissão) não deixa arquivo truncado
    nem apaga o que já estava em ``destino``. Cria as pastas de ``destino``
    que faltam.

    Raises:
        ErroDeGravacaoError: O ``OSError`` da criação das pastas ou da gravação.
    """
    temporario = destino.with_suffix(".tmp")
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario.write_bytes(conteudo)
        temporario.replace(destino)
    except OSError as exc:
        with contextlib.suppress(OSError):
            temporario.unlink(missing_ok=True)
        erro = ErroDeGravacaoError(*exc.args)
        if exc.filename is not None:
            # ``args`` não traz o arquivo, que entra na mensagem.
            erro.filename, erro.filename2 = exc.filename, exc.filename2
        raise erro from exc
    return destino
