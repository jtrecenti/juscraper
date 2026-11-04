"""Prende nos workflows as decisões de CI registradas na #101."""

import re
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((RAIZ / ".github/workflows").glob("*.yml"))
# Workflows cujo resultado barra o PR; o de integração tolera falha de
# tribunal de propósito e fica fora da regra de não silenciar.
BLOQUEANTES = ("changelog.yml", "lint.yml", "quality.yml", "tests.yml")
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
    for opcao in ("--config p/python", "--config p/security-audit", "--metrics=off", "--error"):
        assert opcao in varreduras[0]
    assert varreduras[0].endswith('--baseline-commit "$base" src')


def test_uv_run_nao_refaz_a_resolucao():
    for workflow in WORKFLOWS:
        texto = workflow.read_text(encoding="utf-8")
        if "uv run" not in texto:
            continue
        topo = re.search(r"^env:\n((?:(?:  .*)?\n)+)", texto, re.MULTILINE)
        assert topo, f"{workflow.name} sem env de topo"
        assert '  UV_FROZEN: "1"' in topo.group(1).splitlines(), workflow.name


def test_nenhum_workflow_instala_fora_do_lock():
    proibidos = ("uv pip", "uv add", "pip install", "uv tool install")
    achados = [
        f"{workflow.name}: {linha.strip()}"
        for workflow in WORKFLOWS
        for linha in workflow.read_text(encoding="utf-8").splitlines()
        if not linha.strip().startswith("#") and any(comando in linha for comando in proibidos)
    ]
    assert achados == []


def test_workflows_bloqueantes_nao_silenciam_falha():
    achados = []
    for nome in BLOQUEANTES:
        for linha in linhas(nome):
            if linha.startswith("#"):
                continue
            if "continue-on-error" in linha or "|| true" in linha or "|| :" in linha:
                achados.append(f"{nome}: {linha}")
            if "pytest" in linha and "fail-under" in linha:
                achados.append(f"{nome}: {linha}")
    assert achados == []


def test_perna_de_cobertura_existe_e_roda_o_piso():
    testes = linhas("tests.yml")
    assert "cobertura: true" in testes
    passo = testes.index("run: uv run pytest --cov --cov-report=")
    assert testes[passo - 1] == "if: ${{ matrix.cobertura }}"


def test_dependencias_adicionais_dos_hooks_tem_versao_fixa():
    texto = (RAIZ / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    listas = re.findall(r"additional_dependencies: \[(.*)\]", texto)
    assert listas
    soltas = [item.strip() for lista in listas for item in lista.split(",") if "==" not in item]
    assert soltas == []


def test_changelog_reprova_codigo_sem_entrada_e_aceita_a_etiqueta():
    changelog = linhas("changelog.yml")
    assert "types: [opened, synchronize, reopened, labeled, unlabeled]" in changelog
    assert "DISPENSADO: ${{ contains(github.event.pull_request.labels.*.name, 'sem-changelog') }}" in changelog
    assert 'arquivos="$(git diff --name-only HEAD^1 HEAD)"' in changelog
    assert "if ! grep -q '^src/juscraper/' <<< \"$arquivos\"; then" in changelog
    assert "elif grep -qx 'CHANGELOG.md' <<< \"$arquivos\"; then" in changelog
    assert "exit 1" in changelog
    # O escape documentado é o mesmo que o workflow lê.
    assert "etiqueta `sem-changelog`" in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


def test_so_a_execucao_que_reescreve_a_issue_divide_a_trava_do_relatorio():
    # Num grupo de concorrência, um job pendente cancela o pendente anterior:
    # com o grupo fixo, PRs de tribunais diferentes cancelariam o relatório um
    # do outro.
    integracao = linhas("integration.yml")
    grupos = [linha for linha in integracao if linha.startswith("group:")]
    assert (
        "group: ${{ needs.calendario.outputs.atualizar_issue == 'true' && 'integracao-issue' "
        "|| format('integracao-relatorio-{0}', github.run_id) }}"
    ) in grupos
    assert "atualizar_issue: ${{ env.ATUALIZAR_ISSUE }}" in integracao
