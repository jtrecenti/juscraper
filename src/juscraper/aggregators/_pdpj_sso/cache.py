"""Cache local da credencial do PDPJ e busca da credencial padrao."""
from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from .credencial import CredencialPdpj, utilizavel

logger = logging.getLogger(__name__)

NOME_ARQUIVO = "pdpj_token.json"


def caminho_cache() -> Path:
    """Caminho do cache: ``$XDG_CONFIG_HOME/juscraper/pdpj_token.json``.

    Sem ``XDG_CONFIG_HOME``, usa ``~/.config``. JusBR e PDPJ dividem o arquivo
    porque dividem o token.
    """
    base = os.environ.get("XDG_CONFIG_HOME")
    raiz = Path(base) if base else Path("~/.config").expanduser()
    return raiz / "juscraper" / NOME_ARQUIVO


def salvar_credencial(credencial: CredencialPdpj) -> Path:
    """Grava a credencial no cache, legivel so pelo dono do arquivo.

    ``mkstemp`` cria o temporario ja com permissao ``0o600`` no mesmo
    diretorio do destino, e ``os.replace`` troca o arquivo de uma vez: nem uma
    interrupcao no meio da escrita nem outro usuario da maquina chegam a ver o
    token.
    """
    caminho = caminho_cache()
    caminho.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, nome_temporario = tempfile.mkstemp(dir=caminho.parent, prefix=".pdpj_token.", suffix=".tmp")
    temporario = Path(nome_temporario)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as arquivo:
            json.dump(
                {"access_token": credencial.access_token, "refresh_token": credencial.refresh_token},
                arquivo,
            )
        temporario.replace(caminho)
    except BaseException:
        temporario.unlink(missing_ok=True)
        raise
    return caminho


def carregar_credencial_cache() -> CredencialPdpj | None:
    """Le o cache; arquivo ausente, corrompido ou sem access token vira ``None``."""
    try:
        dados = json.loads(caminho_cache().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict):
        return None
    access = dados.get("access_token")
    refresh = dados.get("refresh_token")
    if not isinstance(access, str) or not access:
        return None
    return CredencialPdpj(access, refresh if isinstance(refresh, str) and refresh else None)


def carregar_credencial_padrao(nomes_env: Sequence[str]) -> tuple[CredencialPdpj, bool] | None:
    """Procura uma credencial utilizavel nas variaveis ``nomes_env`` e depois no cache.

    A ordem de ``nomes_env`` e a precedencia. Variavel de ambiente traz so o
    access token. Candidato vencido ou malformado e ignorado com aviso que cita
    a origem, nunca o token.

    Returns:
        ``(credencial, veio_do_cache)``, ou ``None`` quando nada serve.
    """
    candidatos: list[tuple[str, CredencialPdpj, bool]] = []
    for nome in nomes_env:
        valor = os.environ.get(nome, "").strip()
        if valor:
            candidatos.append((f"variavel de ambiente {nome}", CredencialPdpj(valor), False))
    do_cache = carregar_credencial_cache()
    if do_cache is not None:
        candidatos.append((f"cache {caminho_cache()}", do_cache, True))
    for origem, credencial, veio_do_cache in candidatos:
        if utilizavel(credencial):
            return credencial, veio_do_cache
        logger.warning("Token do PDPJ em %s esta vencido ou malformado; ignorado.", origem)
    return None
