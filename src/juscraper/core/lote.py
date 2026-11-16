"""Laço comum dos downloads em lote.

Usado por ``baixar_acordaos`` e ``baixar_sentencas`` do eSAJ e por
``baixar_inteiros_teores`` do TSE.

Uma linha de entrada vira uma linha de saída, com o caminho do arquivo ou o
motivo da falha. O bloqueio anti-bot vale para a sessão inteira: a primeira
linha que sai :data:`~juscraper.core.failures.MOTIVO_BLOQUEIO_ANTI_BOT`
encerra o lote, e as seguintes saem com o mesmo motivo, sem pedido, por
:func:`~juscraper.core.failures.consultar_em_lote`. Só o raspador que detecta
o bloqueio chega a esse motivo. ``DownloadEmLote.encerrar`` acrescenta outra
condição de parada.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, NamedTuple

import pandas as pd

from juscraper.core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    avisar_falhas,
    consultar_em_lote,
    motivo_falha,
)


@dataclass(frozen=True)
class DownloadEmLote:
    """O que muda entre os downloads em lote.

    Attributes:
        origem: De onde vem a tabela (``"cjsg"``, ``"cjpg"``), para a
            mensagem da coluna que falta.
        colunas: Colunas que o download de uma linha lê.
        erros_com_motivo: Exceções do download com o atributo de classe
            ``motivo``, que vira o motivo da linha.
        coluna_caminho: Coluna com o caminho do arquivo (``None`` na falha).
        descricao: O que falhou, no plural, para o aviso agregado.
        logger: Logger do módulo do download, que registra a falha de cada linha.
        rotulo: Identifica a linha (de ``itertuples``) no log e no aviso agregado.
        encerrar: Recebe os motivos das linhas já processadas (``None`` no
            sucesso) e diz se o lote acaba; as linhas seguintes saem com o
            motivo da última, sem pedido.
    """

    origem: str
    colunas: tuple[str, ...]
    erros_com_motivo: tuple[type[Exception], ...]
    coluna_caminho: str
    descricao: str
    logger: logging.Logger
    rotulo: Callable[[Any], str]
    encerrar: Callable[[list[str | None]], bool] | None = None


class _Download(NamedTuple):
    caminho: str | None
    motivo: str | None


def _pelos_motivos(
    regra: Callable[[list[str | None]], bool] | None,
) -> Callable[[list[_Download]], bool] | None:
    """``regra``, que lê motivos, na forma que :func:`consultar_em_lote` chama."""
    if regra is None:
        return None

    def encerrar(feitos: list[_Download]) -> bool:
        return regra([d.motivo for d in feitos])

    return encerrar


def baixar_em_lote(
    tabela: pd.DataFrame,
    baixar: Callable[[Any], str],
    lote: DownloadEmLote,
    metodo: str,
) -> pd.DataFrame:
    """``tabela`` com ``lote.coluna_caminho`` e :data:`~juscraper.core.failures.COLUNA_MOTIVO_FALHA`.

    Args:
        tabela: Linhas de entrada.
        baixar: Baixa o arquivo de uma linha de ``itertuples`` e devolve o caminho.
        lote: Ver :class:`DownloadEmLote`.
        metodo: Nome qualificado do método público, para o aviso.

    Raises:
        ValueError: ``tabela`` sem alguma das ``lote.colunas``.

    Returns:
        As linhas de ``tabela`` com as duas colunas; as falhas saem também num único ``UserWarning`` ao fim.
    """
    faltando = set(lote.colunas) - set(tabela.columns)
    if faltando:
        raise ValueError(f"{lote.origem} sem as colunas {sorted(faltando)}.")

    def baixar_linha(linha: object) -> _Download:
        try:
            return _Download(baixar(linha), None)
        except lote.erros_com_motivo as erro:
            motivo, mensagem = erro.motivo, str(erro)  # type: ignore[attr-defined]
        except EXCECOES_DE_FALHA_POR_LINHA as erro:
            motivo, mensagem = motivo_falha(erro), str(erro)
        if motivo == MOTIVO_BLOQUEIO_ANTI_BOT:
            lote.logger.warning(
                "%s: bloqueio anti-bot em %s; o lote para aqui: %s", metodo, lote.rotulo(linha), mensagem
            )
        else:
            lote.logger.info("%s: %s", lote.rotulo(linha), mensagem)
        return _Download(None, motivo)

    linhas = list(tabela.itertuples(index=False))
    encerrar = _pelos_motivos(lote.encerrar)
    downloads = consultar_em_lote(
        linhas, baixar_linha, lambda motivo: _Download(None, motivo), sleep_time=0, encerrar=encerrar
    )
    falhas = [f"{lote.rotulo(linha)}: {d.motivo}" for linha, d in zip(linhas, downloads, strict=True) if d.motivo]
    avisar_falhas(falhas, metodo, lote.descricao)
    return tabela.assign(
        **{lote.coluna_caminho: [d.caminho for d in downloads], COLUNA_MOTIVO_FALHA: [d.motivo for d in downloads]}
    )
