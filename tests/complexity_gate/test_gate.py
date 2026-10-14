"""Exercita o gate de complexidade com Git, Lizard e Complexipy reais em repositórios temporários."""

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]


def aninhada(nome, niveis, marca=""):
    """Função com ``niveis`` ``if`` encaixados: cognitiva 15, 21 e 28 para 5, 6 e 7 níveis."""
    linhas = [f"def {nome}(valores):{marca}"]
    recuo = "    "
    for nivel in range(niveis):
        linhas.append(f"{recuo}if valores[{nivel}]:")
        recuo += "    "
    linhas.extend([f"{recuo}return {niveis}", "    return 0"])
    return "\n".join(linhas) + "\n"


def em_cadeia(nome, termos):
    """Função plana com ``termos`` operandos de ``or``: ciclomática ``termos``, cognitiva 1."""
    return f"def {nome}(valores):\n    return " + " or ".join(f"valores[{i}]" for i in range(termos)) + "\n"


def gravar(raiz, *funcoes):
    (raiz / "src/modulo.py").write_text("\n\n".join(funcoes), encoding="utf-8")


def git(raiz, *argumentos):
    return subprocess.run(
        ["git", *argumentos], cwd=raiz, check=True, capture_output=True, text=True,
    ).stdout.strip()


def registrar_base(raiz):
    git(raiz, "add", ".")
    git(raiz, "-c", "user.name=Teste", "-c", "user.email=teste@example.com",
        "-c", "commit.gpgsign=false", "commit", "-qm", "Base de teste")
    git(raiz, "update-ref", "refs/remotes/origin/main", "HEAD")


def executar_gate(raiz, *argumentos):
    return subprocess.run(
        [sys.executable, str(raiz / "scripts/check_complexity.py"), *argumentos],
        cwd=raiz, check=False, capture_output=True, text=True,
    )


@pytest.fixture
def repositorio(tmp_path):
    for diretorio in ("src", "scripts"):
        (tmp_path / diretorio).mkdir()
    shutil.copyfile(RAIZ / "scripts/check_complexity.py", tmp_path / "scripts/check_complexity.py")
    gravar(tmp_path, aninhada("legada", 6), aninhada("simples", 2))
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.hooksPath", "/dev/null")
    registrar_base(tmp_path)
    return tmp_path


def test_divida_legada_inalterada_passa(repositorio):
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr
    assert "Complexidade dentro da régua" in resultado.stdout


def test_funcao_nova_acima_do_teto_falha(repositorio):
    gravar(repositorio, aninhada("legada", 6), aninhada("simples", 2), aninhada("nova", 6))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert re.search(r"NEW\s+src/modulo\.py::nova\s+21", resultado.stderr)


def test_funcao_nova_no_teto_passa(repositorio):
    gravar(repositorio, aninhada("legada", 6), aninhada("simples", 2), aninhada("nova", 5))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_funcao_legada_que_piora_falha(repositorio):
    gravar(repositorio, aninhada("legada", 7), aninhada("simples", 2))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert re.search(r"REGRESSED\s+src/modulo\.py::legada\s+21 → 28", resultado.stderr)


def test_funcao_que_cruza_o_teto_falha(repositorio):
    gravar(repositorio, aninhada("legada", 6), aninhada("simples", 6))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert re.search(r"REGRESSED\s+src/modulo\.py::simples\s+3 → 21", resultado.stderr)


def test_funcao_legada_que_melhora_sem_chegar_ao_teto_passa(repositorio):
    gravar(repositorio, aninhada("legada", 7), aninhada("simples", 2))
    registrar_base(repositorio)
    gravar(repositorio, aninhada("legada", 6), aninhada("simples", 2))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_dispensa_por_comentario_nao_esconde_funcao_nova(repositorio):
    nova = aninhada("nova", 6, "  # noqa: complexipy")
    gravar(repositorio, aninhada("legada", 6), aninhada("simples", 2), nova)
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "src/modulo.py::nova" in resultado.stderr


def test_ciclomatica_acima_do_teto_falha_mesmo_sem_mudanca(repositorio):
    gravar(repositorio, aninhada("legada", 6), em_cadeia("plana", 16))
    registrar_base(repositorio)
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert re.search(r"plana has \d+ NLOC, 16 CCN", resultado.stderr)


def test_ciclomatica_no_teto_passa(repositorio):
    gravar(repositorio, aninhada("legada", 6), em_cadeia("plana", 15))
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_ramo_atras_da_main_nao_herda_melhoria_dela(repositorio):
    saida_do_ramo = git(repositorio, "rev-parse", "HEAD")
    gravar(repositorio, aninhada("legada", 2), aninhada("simples", 2))
    registrar_base(repositorio)
    git(repositorio, "checkout", "-q", "--detach", saida_do_ramo)
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_base_inexistente_falha(repositorio):
    resultado = executar_gate(repositorio, "--base-ref", "referencia-inexistente")
    assert resultado.returncode == 1
    assert "Falha ao consultar a base Git" in resultado.stderr


def test_workflow_compara_o_pr_com_a_ponta_da_branch_de_destino():
    linhas = (RAIZ / ".github/workflows/quality.yml").read_text(encoding="utf-8").splitlines()
    bases = [
        linha.split(":", 1)[1].strip() for linha in linhas if linha.strip().startswith("COMPLEXITY_BASE:")
    ]
    assert bases == [
        "${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || github.event.before }}",
    ]
    # A variável só protege se toda chamada do gate a usar como base.
    chamadas = [linha.strip() for linha in linhas if "check_complexity.py" in linha]
    assert chamadas
    assert all(chamada.endswith('check_complexity.py --base-ref "$COMPLEXITY_BASE"') for chamada in chamadas)


def test_versoes_das_ferramentas_iguais_no_extra_dev_e_no_pre_commit():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    fixadas = dict(item.split("==") for item in projeto["optional-dependencies"]["dev"] if "==" in item)
    pre_commit = (RAIZ / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook = re.search(r"id: complexity\n(?:\s+.+\n)*?\s+additional_dependencies: \[(.+)\]", pre_commit)
    assert hook, "hook complexity sem additional_dependencies"
    no_hook = dict(item.strip().split("==") for item in hook.group(1).split(","))
    assert no_hook == {"lizard": fixadas["lizard"], "complexipy": fixadas["complexipy"]}
