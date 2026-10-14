"""Prende nos workflows as decisões de CI registradas na #101."""

import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((RAIZ / ".github/workflows").glob("*.yml"))
BASE_DO_EVENTO = (
    "${{ github.event_name == 'pull_request' && format('origin/{0}', github.base_ref) || github.event.before }}"
)


def linhas(nome):
    return [linha.strip() for linha in (RAIZ / ".github/workflows" / nome).read_text(encoding="utf-8").splitlines()]


def test_toda_instalacao_usa_o_lock():
    instalacoes = [
        f"{workflow.name}: {linha.strip()}"
        for workflow in WORKFLOWS
        for linha in workflow.read_text(encoding="utf-8").splitlines()
        if "uv sync" in linha and not linha.strip().startswith("#")
    ]
    assert len(instalacoes) >= 5
    assert [instalacao for instalacao in instalacoes if "--frozen" not in instalacao] == []


def test_lock_versionado_e_conferido():
    assert (RAIZ / "uv.lock").is_file()
    ignorados = [linha.strip() for linha in (RAIZ / ".gitignore").read_text(encoding="utf-8").splitlines()]
    assert "uv.lock" not in ignorados
    assert "run: uv lock --check" in linhas("lint.yml")


def test_piso_de_cobertura():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert projeto["tool"]["coverage"]["report"]["fail_under"] == 94


def test_pre_commit_roda_todos_os_hooks_no_ci():
    lint = linhas("lint.yml")
    assert "run: uv run pre-commit run --all-files --show-diff-on-failure" in lint
    assert [linha for linha in lint if linha.startswith("SKIP:")] == ["SKIP: lint-policy,complexity"]


def test_semgrep_reprova_so_achado_novo():
    qualidade = linhas("quality.yml")
    bases = [linha.split(":", 1)[1].strip() for linha in qualidade if linha.startswith("SEMGREP_BASE:")]
    assert bases == [BASE_DO_EVENTO]
    assert 'base="$(git merge-base HEAD "$SEMGREP_BASE")"' in qualidade
    varreduras = [linha for linha in qualidade if "semgrep==" in linha]
    assert len(varreduras) == 1
    for opcao in ("--config p/python", "--config p/security-audit", "--metrics=off", "--error",
                  '--baseline-commit "$base"'):
        assert opcao in varreduras[0]
