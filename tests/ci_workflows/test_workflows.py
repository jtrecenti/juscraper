"""Prende nos workflows as decisões de CI registradas na #101."""

import re
import tomllib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((RAIZ / ".github/workflows").glob("*.yml"))
# Workflows cujo resultado barra o PR; o de integração tolera falha de
# tribunal de propósito e fica fora da regra de não silenciar.
BLOQUEANTES = ("changelog.yml", "lint.yml", "quality.yml", "tests.yml")
# A única instalação fora do lock: a perna do piso do pandas troca o pandas do
# lock pela série do piso declarado no pyproject.toml.
INSTALACAO_DO_PISO = 'uv pip install "pandas==2.0.*" "numpy<2"'
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


def test_pre_commit_no_ci_pula_so_o_que_roda_em_outro_passo():
    lint = linhas("lint.yml")
    assert 'uv export --extra dev --no-hashes --no-emit-project --quiet -o "$RUNNER_TEMP/restricoes.txt"' in lint
    assert (
        'uvx --python 3.12 --constraints "$RUNNER_TEMP/restricoes.txt" '
        "pre-commit run --all-files --show-diff-on-failure"
    ) in lint
    assert [linha for linha in lint if linha.startswith("SKIP:")] == ["SKIP: lint-policy,complexity,pytest"]


def test_job_pre_commit_pula_os_hooks_que_usam_o_ambiente_do_projeto():
    # O job roda o pre-commit pelo uvx, sem o extra dev: um hook que roda fora
    # do ambiente próprio montado pelo pre-commit não acharia o projeto.
    config = yaml.safe_load((RAIZ / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    fora_do_ambiente_proprio = {
        hook["id"]
        for repo in config["repos"]
        for hook in repo.get("hooks", [])
        if hook.get("language") in {"system", "script", "unsupported", "unsupported_script"}
    }
    assert fora_do_ambiente_proprio
    (skip,) = [linha.split(":", 1)[1].strip() for linha in linhas("lint.yml") if linha.startswith("SKIP:")]
    assert fora_do_ambiente_proprio <= set(skip.split(","))


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
    assert achados == [f"tests.yml: run: {INSTALACAO_DO_PISO}"]


def test_perna_do_piso_do_pandas_roda_o_piso_do_pyproject():
    projeto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    (pandas,) = [dep for dep in projeto["project"]["dependencies"] if dep.startswith("pandas")]
    piso = re.match(r"pandas\s*>=\s*(\d+\.\d+)", pandas)
    assert piso, f"piso do pandas não reconhecido em {pandas!r}"
    assert f'"pandas=={piso.group(1)}.*"' in INSTALACAO_DO_PISO, "a perna não instala a série do piso do pandas"
    jobs = yaml.safe_load((RAIZ / ".github/workflows/tests.yml").read_text(encoding="utf-8"))["jobs"]
    passos = jobs["pytest-piso-pandas"]["steps"]
    # A perna roda no menor Python suportado (o motivo está no tests.yml).
    python_minimo = re.fullmatch(r">=\s*(\d+\.\d+)", projeto["project"]["requires-python"])
    assert python_minimo, projeto["project"]["requires-python"]
    pythons = [passo["with"]["python-version"] for passo in passos if "setup-uv" in passo.get("uses", "")]
    assert pythons == [python_minimo.group(1)]
    runs = [passo.get("run") for passo in passos]
    # Sem --no-sync, o uv run devolveria o pandas do lock antes do pytest.
    assert runs[-3:] == ["uv sync --frozen --extra dev", INSTALACAO_DO_PISO, "uv run --no-sync pytest -n auto"]
    assert set(jobs["obrigatorios"]["needs"]) == {"pytest", "pytest-piso-pandas"}


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
    passo = testes.index("run: uv run pytest -n auto --cov --cov-report=")
    assert testes[passo - 1] == "if: ${{ matrix.cobertura }}"


def test_pernas_sem_cobertura_rodam_a_suite_offline():
    testes = linhas("tests.yml")
    passo = testes.index("run: uv run pytest -n auto")
    assert testes[passo - 1] == "if: ${{ !matrix.cobertura }}"


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
    # O escape documentado é o mesmo que o workflow lê.
    assert "etiqueta `sem-changelog`" in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")


def test_so_quem_pede_para_reescrever_a_issue_divide_a_trava_do_relatorio():
    # Num grupo de concorrência, um job pendente cancela o pendente anterior:
    # com o grupo fixo, disparos de tribunais diferentes cancelariam o
    # relatório um do outro.
    integracao = linhas("integration.yml")
    grupos = [linha for linha in integracao if linha.startswith("group:")]
    assert grupos == [
        "group: ${{ inputs.atualizar_issue && 'integracao-issue' "
        "|| format('integracao-relatorio-{0}', github.run_id) }}",
    ]
    assert (
        "ATUALIZAR_ISSUE: ${{ inputs.atualizar_issue && inputs.tribunal == '' && github.ref == 'refs/heads/main' }}"
    ) in integracao


def test_integracao_so_roda_por_disparo_manual():
    # Decisão de 14/11/2026: os tribunais bloqueiam os IPs dos runners, então
    # a integração ao vivo não roda sozinha em PR nem por agendamento; a
    # conferência de rotina é local, de IP residencial.
    texto = (RAIZ / ".github/workflows/integration.yml").read_text(encoding="utf-8")
    # O YAML 1.1 lê a chave `on` como o booleano True.
    assert list(yaml.safe_load(texto)[True]) == ["workflow_dispatch"]


def test_filtros_de_caminho_apontam_para_arquivos_existentes():
    # Um filtro `paths` com caminho inexistente nunca casa e deixa de disparar
    # o workflow em silêncio (o docs.yml já apontou para um docs-publish.yml).
    padroes = []
    for workflow in WORKFLOWS:
        eventos = yaml.safe_load(workflow.read_text(encoding="utf-8"))[True]
        if not isinstance(eventos, dict):
            continue
        for nome, config in eventos.items():
            for chave in ("paths", "paths-ignore"):
                padroes += [(workflow.name, nome, padrao) for padrao in (config or {}).get(chave, [])]
    assert padroes
    assert [p for p in padroes if not any(RAIZ.glob(p[2].removeprefix("!")))] == []
