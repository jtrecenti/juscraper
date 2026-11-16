"""Checkpoint da busca do Falcao: páginas e manifesto num diretório retomável.

O backend bloqueia o IP por cota diária, e uma coleta grande atravessa mais de
um dia. O checkpoint guarda cada página recebida em
``{colecao}_{pagina:04d}.json`` e, em :data:`MANIFESTO`, a busca a que as
páginas pertencem e o último ``quantidadeTotal`` observado. A página concluída
é o arquivo presente com a lista ``documentos``: a retomada requisita só as
que faltam.
"""
from __future__ import annotations

import json
from pathlib import Path

from ...core.avisos import avisar
from ...core.download import gravar_arquivo
from .download import identidade_da_busca

MANIFESTO = "manifest.json"

_VERSAO = 1


def gravar_json(arquivo: Path, conteudo: dict) -> None:
    """Grava por troca atômica: arquivo truncado não passa por página concluída."""
    gravar_arquivo(json.dumps(conteudo, ensure_ascii=False).encode("utf-8"), arquivo)


def _gravar_manifesto(diretorio: Path, identidade: dict, total: int | None) -> None:
    """Registra a busca do checkpoint e o último total observado."""
    gravar_json(diretorio / MANIFESTO, {"version": _VERSAO, "identity": identidade, "total": total})


def _abrir(diretorio: Path, identidade: dict, *, resume: bool) -> int | None:
    """Cria o checkpoint ou valida o existente; devolve o total da sessão anterior."""
    if not resume:
        if diretorio.exists() and (not diretorio.is_dir() or any(diretorio.iterdir())):
            raise ValueError(
                f"checkpoint_dir ocupado ({diretorio}); use resume=True para continuar a coleta "
                "ou outro diretório para uma coleta nova."
            )
        _gravar_manifesto(diretorio, identidade, None)
        return None
    corrompido = f"Checkpoint inexistente ou corrompido em {diretorio}"
    try:
        manifesto = json.loads((diretorio / MANIFESTO).read_text(encoding="utf-8"))
        versao, anterior, total = manifesto["version"], manifesto["identity"], manifesto["total"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"{corrompido}: {exc}") from exc
    if versao != _VERSAO or not isinstance(anterior, dict) or not isinstance(total, (int, type(None))):
        raise ValueError(f"{corrompido}: manifesto fora do formato esperado.")
    # O manifesto pode ser anterior à ordenação dos filtros em lista na identidade.
    anterior = identidade_da_busca(anterior)
    if anterior != identidade:
        diferentes = sorted(k for k in anterior.keys() | identidade.keys() if anterior.get(k) != identidade.get(k))
        raise ValueError(
            f"Checkpoint incompatível com a busca: {diretorio} guarda outra busca "
            f"(parâmetros do backend que diferem: {', '.join(diferentes)}). "
            "Repita os mesmos filtros ou use outro diretório."
        )
    return total


def _tem_documentos(arquivo: Path) -> bool:
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(dados, dict) and isinstance(dados.get("documentos"), list)


def _paginas_gravadas(diretorio: Path, colecao: str) -> set[int]:
    """Números (1-based) das páginas concluídas do checkpoint.

    Resposta gravada sem a lista ``documentos`` (envelope de erro) não conta:
    a retomada a requisita de novo, em vez de deixar um buraco no resultado.
    """
    gravadas = set()
    for arquivo in diretorio.glob(f"{colecao}_*.json"):
        numero = arquivo.stem.rsplit("_", 1)[1]
        if numero.isdigit() and _tem_documentos(arquivo):
            gravadas.add(int(numero))
    return gravadas


class Checkpoint:
    """Estado de uma coleta retomável, validado antes de qualquer requisição.

    Args:
        diretorio: Pasta do checkpoint.
        identidade: Parâmetros da busca enviados ao backend, sem página nem
            sessão. ``colecao`` entra no nome dos arquivos de página.
        resume: ``False`` exige pasta ausente ou vazia; ``True`` exige o
            manifesto de uma busca com a mesma ``identidade``.

    Raises:
        ValueError: Pasta ocupada sem ``resume``; checkpoint inexistente,
            corrompido ou de outra busca com ``resume``.
    """

    def __init__(self, diretorio: Path, identidade: dict, *, resume: bool) -> None:
        self.diretorio = diretorio
        self.identidade = identidade
        self.total = _abrir(diretorio, identidade, resume=resume)
        self.gravadas = _paginas_gravadas(diretorio, identidade["colecao"])

    def observar(self, total: int) -> None:
        """Registra o total da sessão e avisa se ele mudou com páginas já gravadas."""
        anterior, self.total = self.total, total
        _gravar_manifesto(self.diretorio, self.identidade, total)
        if self.gravadas and anterior is not None and total != anterior:
            avisar(
                f"O total da busca no Falcao mudou de {anterior} para {total} desde a sessão anterior. "
                f"As páginas já gravadas em {self.diretorio} foram mantidas e podem repetir ou omitir "
                "documentos em relação às novas; confira duplicatas antes de usar o resultado.",
                UserWarning,
            )
