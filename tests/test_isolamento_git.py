"""A suíte não grava no repositório indicado pelas variáveis ``GIT_*`` do ambiente."""
import os
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_gates_nao_gravam_no_repositorio_do_ambiente(tmp_path):
    """Como dentro de um hook do git: ``GIT_DIR`` aponta para outro repositório."""
    alheio = tmp_path / "alheio.git"
    subprocess.run(["git", "init", "-q", "--bare", str(alheio)], check=True)
    ambiente = {**os.environ, "GIT_DIR": str(alheio), "GIT_INDEX_FILE": str(tmp_path / "index")}

    resultado = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider",
         "tests/lint_policy/test_policy.py::test_codigo_antigo_passa_com_a_dispensa_existente"],
        cwd=RAIZ, env=ambiente, capture_output=True, text=True, check=False,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    def git_alheio(*argumentos):
        return subprocess.run(
            ["git", "--git-dir", str(alheio), *argumentos], capture_output=True, text=True, check=False,
        ).stdout

    assert git_alheio("for-each-ref") == ""
    assert git_alheio("config", "--get", "core.hooksPath") == ""
