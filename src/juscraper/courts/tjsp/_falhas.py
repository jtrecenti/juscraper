"""Linhas de falha da consulta processual do TJSP (``cpopg`` e ``cposg``).

O processo que não foi baixado, ou cujo arquivo não pôde ser lido, fica no
resultado numa linha com ``motivo_falha`` (#460). Os helpers aqui servem aos
dois graus.

O download grava as falhas em :data:`ARQUIVO_FALHAS`, na pasta do grau, e o
parse as lê de lá: assim o fluxo em duas etapas (``cpopg_download`` e depois
``cpopg_parse``) devolve as mesmas linhas de falha que o ``cpopg``.
"""
from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path

import pandas as pd

from ...core.avisos import avisar
from ...core.exceptions import BloqueioAntiBotWarning
from ...core.failures import (
    COLUNA_MOTIVO_FALHA,
    EXCECOES_DE_FALHA_POR_LINHA,
    MOTIVO_BLOQUEIO_ANTI_BOT,
    MOTIVO_NAO_ENCONTRADO,
    MOTIVO_RESPOSTA_INESPERADA,
    motivo_falha,
    resumir_falhas,
)
from ...utils.cnj import clean_cnj, format_cnj


def cnj_invalido(id_cnj: object) -> bool:
    """Entrada que não é texto com 20 dígitos: sai ``entrada_invalida`` sem requisição."""
    return not isinstance(id_cnj, str) or len(clean_cnj(id_cnj)) != 20


def motivo_do_processo(erro: BaseException) -> str:
    """Motivo de falha do processo cujo download falhou.

    O ``RuntimeError`` das tentativas esgotadas traz o último erro em
    ``__cause__``, e é dele que sai o motivo. Erro sem motivo no vocabulário
    (página fora do formato, código de processo inválido) vira
    ``resposta_inesperada``.
    """
    for candidato in (erro, erro.__cause__):
        if candidato is not None and isinstance(candidato, EXCECOES_DE_FALHA_POR_LINHA):
            with suppress(TypeError):
                return motivo_falha(candidato)
    return MOTIVO_RESPOSTA_INESPERADA


def avisar_falhas_de_processo(sem_arquivo: dict, ilegiveis: list[str], metodo: str, onde: str) -> None:
    """Um único ``UserWarning`` com os processos sem arquivo e os arquivos ilegíveis, se houver.

    Sai como :class:`BloqueioAntiBotWarning` quando algum motivo é
    ``bloqueio_anti_bot``, como em :func:`juscraper.core.failures.avisar_falhas`.

    Args:
        sem_arquivo: ``{CNJ formatado: motivo}``, como devolvem os downloads.
        ilegiveis: Uma entrada por arquivo que o parse recusou, já com o motivo.
        metodo: Método público que abre a mensagem.
        onde: Onde as falhas saem com ``motivo_falha``, como
            ``"Eles saem na tabela basicos"``.
    """
    entradas = [f"{cnj}: {motivo}" for cnj, motivo in sem_arquivo.items()] + ilegiveis
    if not entradas:
        return
    descricao = " ou ".join(
        nome for nome, itens in (("consulta(s) de processo", sem_arquivo), ("leitura(s) de arquivo", ilegiveis))
        if itens
    )
    mensagem = f"{metodo}: {resumir_falhas(entradas, descricao)} {onde}, com o motivo em motivo_falha."
    if MOTIVO_NAO_ENCONTRADO in sem_arquivo.values():
        mensagem += (
            f" {MOTIVO_NAO_ENCONTRADO}: a consulta pública não mostra o número, que pode não existir "
            "ou estar em segredo de justiça."
        )
    avisar(mensagem, BloqueioAntiBotWarning if MOTIVO_BLOQUEIO_ANTI_BOT in sem_arquivo.values() else UserWarning)


ARQUIVO_FALHAS = "falhas_download.json"
"""``{CNJ formatado: motivo}`` dos processos sem arquivo, em ``<download>/cpopg`` ou ``<download>/cposg``."""


def chave_do_registro(cnj: object) -> str:
    """Chave de ``cnj`` no registro de falhas: o CNJ formatado, ou a entrada como ``str`` sem 20 dígitos."""
    return str(format_cnj(cnj, strict=False))  # type: ignore[call-overload]  # entrada fora de str: "None", "123"


def registrar_falhas(pasta: Path, pedidos: list, falhas: dict) -> None:
    """Grava em ``pasta`` as falhas do lote, para o parse as devolver como linhas.

    Os CNJs ``pedidos``, como vieram do usuário, saem do registro antes de as ``falhas`` entrarem: o
    processo baixado agora não guarda a falha de um download anterior na
    mesma pasta. A entrada que não é texto (``None``, número) entra como
    ``str``, a única chave que o JSON guarda. Registro vazio apaga o arquivo;
    o arquivo é trocado de uma vez, e um download interrompido não o deixa
    pela metade.
    """
    arquivo = pasta / ARQUIVO_FALHAS
    registro = _ler_registro(arquivo)
    for cnj in pedidos:
        registro.pop(chave_do_registro(cnj), None)
    registro.update({str(cnj): motivo for cnj, motivo in falhas.items()})
    if not registro:
        arquivo.unlink(missing_ok=True)
        return
    pasta.mkdir(parents=True, exist_ok=True)
    temporario = arquivo.with_suffix(".tmp")
    temporario.write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    temporario.replace(arquivo)


def processos_sem_arquivo(pasta: Path, arquivos: list[Path]) -> dict[str, str]:
    """As falhas registradas em ``pasta``, menos as dos CNJs que têm arquivo em ``arquivos``.

    O processo baixado antes e que falhou num download seguinte na mesma
    pasta sai pelo arquivo que já estava lá, e não numa segunda linha, de falha.
    """
    com_arquivo = {cnj_da_pasta(arquivo) for arquivo in arquivos}
    return {cnj: motivo for cnj, motivo in _ler_registro(pasta / ARQUIVO_FALHAS).items() if cnj not in com_arquivo}


def _ler_registro(arquivo: Path) -> dict[str, str]:
    if not arquivo.is_file():
        return {}
    registro: dict[str, str] = json.loads(arquivo.read_text(encoding="utf-8"))
    return registro


def so_os_pedidos(
    arquivos: list[Path], sem_arquivo: dict[str, str], pedidos: list | None,
) -> tuple[list[Path], dict[str, str]]:
    """Os arquivos e as falhas dos CNJs ``pedidos``; tudo, com ``pedidos`` ``None``.

    O ``cpopg`` e o ``cposg`` compostos leem a pasta de download inteira, que
    pode guardar processos e falhas de um ``*_download`` anterior: só os
    números do lote entram no resultado, pela :func:`chave_do_registro`.
    """
    if pedidos is None:
        return arquivos, sem_arquivo
    chaves = {chave_do_registro(cnj) for cnj in pedidos}
    return (
        [arquivo for arquivo in arquivos if cnj_da_pasta(arquivo) in chaves],
        {cnj: motivo for cnj, motivo in sem_arquivo.items() if cnj in chaves},
    )


def cnj_da_pasta(arquivo: Path) -> str | None:
    """CNJ formatado da pasta do processo (``<download>/<cnj limpo>/<arquivo>.html``); ``None`` fora dela."""
    nome = arquivo.parent.name
    return format_cnj(nome) if nome.isdigit() and len(nome) == 20 else None


def com_linhas_de_falha(tabela: pd.DataFrame, falhas: list[dict]) -> pd.DataFrame:
    """Acrescenta a ``tabela`` as linhas de falha e, se faltar, a coluna ``motivo_falha``, ``None`` nas linhas lidas.

    Cada falha é um ``dict`` com ``motivo_falha`` e as colunas que a
    identificam (o CNJ, o arquivo); as demais colunas saem ``None``.
    """
    if COLUNA_MOTIVO_FALHA not in tabela.columns:
        tabela = tabela.assign(**{COLUNA_MOTIVO_FALHA: None})
    if not falhas:
        return tabela
    linhas = pd.DataFrame(falhas, columns=tabela.columns, dtype=object)
    if tabela.empty:
        return linhas
    return pd.concat([tabela, linhas], ignore_index=True)
