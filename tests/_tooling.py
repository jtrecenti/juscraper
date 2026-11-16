"""Operações mínimas compartilhadas pelos testes de scripts e gates."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


def carregar_script(nome: str, caminho: Path) -> ModuleType:
    """Importa um script pelo caminho com nome isolado, sem chamar ``main``."""
    spec = importlib.util.spec_from_file_location(nome, caminho)
    assert spec is not None
    assert spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def git_saida(raiz: Path, *argumentos: str) -> str:
    """Executa Git no repositório temporário e devolve stdout sem espaço externo."""
    return subprocess.run(
        ["git", *argumentos], cwd=raiz, check=True, capture_output=True, text=True,
    ).stdout.strip()
