"""Executa com bash os blocos ``run:`` dos workflows de integração, de changelog e de testes.

Ler o texto do YAML não prende o comportamento: reverter um código de saída ou
a montagem do alvo deixaria as linhas conferidas no lugar. Aqui cada bloco roda
como no runner (``bash -eo pipefail``), com um ``uv`` falso no PATH que devolve
o código de saída pedido e um repositório git com commit de merge, como o
checkout de PR.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOWS = RAIZ / ".github" / "workflows"


def bloco_run(workflow, passo):
    """Devolve o script do passo ``- name: <passo>``, sem a indentação do YAML."""
    linhas = (WORKFLOWS / workflow).read_text(encoding="utf-8").splitlines()
    inicio = next(i for i, linha in enumerate(linhas) if linha.strip() == f"- name: {passo}")
    run = next(i for i in range(inicio, len(linhas)) if linhas[i].strip() == "run: |")
    recuo = len(linhas[run + 1]) - len(linhas[run + 1].lstrip())
    corpo = []
    for linha in linhas[run + 1:]:
        if linha.strip() and len(linha) - len(linha.lstrip()) < recuo:
            break
        corpo.append(linha)
    return textwrap.dedent("\n".join(corpo)) + "\n"


def rodar(script, pasta, **ambiente):
    """Roda o script como o runner e devolve ``(código, saídas gravadas em GITHUB_OUTPUT)``."""
    saida = pasta / "github_output"
    saida.write_text("", encoding="utf-8")
    env = {**os.environ, "GITHUB_OUTPUT": str(saida), **ambiente}
    resultado = subprocess.run(
        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script],
        cwd=pasta, env=env, capture_output=True, text=True, check=False,
    )
    gravadas = dict(linha.split("=", 1) for linha in saida.read_text(encoding="utf-8").splitlines() if "=" in linha)
    return resultado.returncode, gravadas, resultado.stdout + resultado.stderr


@pytest.fixture
def uv_falso(tmp_path):
    """Põe no PATH um ``uv`` que grava os argumentos e sai com ``$CODIGO_UV``."""
    pasta = tmp_path / "bin"
    pasta.mkdir()
    uv = pasta / "uv"
    uv.write_text('#!/bin/bash\necho "$@" >> "$ARGS_UV"\nexit "${CODIGO_UV:-0}"\n', encoding="utf-8")
    uv.chmod(0o755)
    return {"PATH": f"{pasta}{os.pathsep}{os.environ['PATH']}", "ARGS_UV": str(tmp_path / "args_uv")}


@pytest.fixture
def arvore(tmp_path):
    for nome in ("tjmt", "jusbr", "tjrs", "tjto"):
        (tmp_path / "tests" / nome).mkdir(parents=True)
        (tmp_path / "docs" / "notebooks").mkdir(parents=True, exist_ok=True)
        (tmp_path / "docs" / "notebooks" / f"{nome}.ipynb").write_text("{}", encoding="utf-8")
    return tmp_path


AMBIENTE_DO_ALVO = {"NOTEBOOKS_COM_CREDENCIAL": "jusbr pdpj", "FORA_DO_CI": "tjrs", "PAUSA_TJTO": "900"}


@pytest.mark.parametrize(
    ("ambiente", "pausa"),
    [
        ({"TRIBUNAL": "tjmt tjto"}, "900"),
        ({"TRIBUNAL": "tjmt\ttjto"}, "900"),
        ({"TRIBUNAL": "tjmt"}, ""),
        # Execução completa: o TJTO roda, a menos que esteja em FORA_DO_CI.
        ({"TRIBUNAL": ""}, "900"),
        ({"TRIBUNAL": "", "FORA_DO_CI": "tjrs tjto"}, ""),
        # A execução dirigida ignora a lista FORA_DO_CI.
        ({"TRIBUNAL": "tjto", "FORA_DO_CI": "tjrs tjto"}, "900"),
    ],
    ids=[
        "dirigida-com-tjto", "dirigida-com-tab", "dirigida-sem-tjto",
        "completa", "completa-sem-tjto", "dirigida-ignora-a-lista",
    ],
)
def test_alvo_pede_a_pausa_do_tjto_so_quando_ele_roda(arvore, ambiente, pausa):
    codigo, saidas, log = rodar(
        bloco_run("integration.yml", "Resolver o alvo"), arvore, **{**AMBIENTE_DO_ALVO, **ambiente},
    )

    assert codigo == 0, log
    assert saidas["pausa_tjto"] == pausa


@pytest.mark.parametrize(
    "passo", ["Esperar o WAF do TJTO antes dos notebooks", "Esperar o WAF do TJTO antes do teste release"]
)
def test_pausa_do_tjto_espera_os_segundos_pedidos(tmp_path, passo):
    pasta = tmp_path / "bin"
    pasta.mkdir()
    (pasta / "sleep").write_text('#!/bin/bash\necho "$@" > "$ESPERA"\n', encoding="utf-8")
    (pasta / "sleep").chmod(0o755)
    espera = tmp_path / "espera"

    codigo, _, log = rodar(
        bloco_run("integration.yml", passo), tmp_path,
        PAUSA="900", ESPERA=str(espera), PATH=f"{pasta}{os.pathsep}{os.environ['PATH']}",
    )

    assert codigo == 0, log
    assert espera.read_text(encoding="utf-8").split() == ["900"]


def test_alvo_dirigido_monta_testes_notebooks_e_release(arvore):
    codigo, saidas, log = rodar(
        bloco_run("integration.yml", "Resolver o alvo"), arvore, TRIBUNAL="tjmt jusbr", **AMBIENTE_DO_ALVO,
    )

    assert codigo == 0, log
    assert saidas["testes"].split() == ["tests/tjmt", "tests/jusbr"]
    # Notebook com credencial fica de fora; a lista FORA_DO_CI não vale aqui.
    assert saidas["notebooks"].split() == ["docs/notebooks/tjmt.ipynb"]
    assert saidas["release"] == "tjmt or jusbr"
    assert "--ignore=tests/tjrs" not in saidas["ignorar_testes"]


def test_alvo_completo_ignora_fora_do_ci_e_nao_roda_release(arvore):
    codigo, saidas, log = rodar(
        bloco_run("integration.yml", "Resolver o alvo"), arvore, TRIBUNAL="", **AMBIENTE_DO_ALVO,
    )

    assert codigo == 0, log
    assert (saidas["testes"], saidas["notebooks"], saidas["release"]) == ("tests", "docs/notebooks", "")
    assert "--ignore=tests/tjrs" in saidas["ignorar_testes"].split()
    assert "--ignore=docs/notebooks/jusbr.ipynb" in saidas["ignorar_notebooks"].split()


@pytest.mark.parametrize("tribunal", [" ", "../tjmt", "tjzz", "tjmt $(id)"])
def test_alvo_recusa_nome_que_nao_e_diretorio_de_testes(arvore, tribunal):
    codigo, _, log = rodar(
        bloco_run("integration.yml", "Resolver o alvo"), arvore, TRIBUNAL=tribunal, **AMBIENTE_DO_ALVO,
    )

    assert codigo == 1, log
    assert "::error::" in log


# (passo, alvo, código do pytest, código do passo). Na execução completa a
# falha de teste (1) passa; na dirigida reprova. 5 é tribunal sem teste na
# dirigida e alvo errado na completa.
CODIGOS = [
    ("Rodar os testes de integração", "", 0, 0),
    ("Rodar os testes de integração", "", 1, 0),
    ("Rodar os testes de integração", "", 2, 2),
    ("Rodar os testes de integração", "", 5, 5),
    ("Rodar os testes de integração", "tjmt", 0, 0),
    ("Rodar os testes de integração", "tjmt", 1, 1),
    ("Rodar os testes de integração", "tjmt", 2, 2),
    ("Rodar os testes de integração", "tjmt", 5, 0),
    ("Rodar os notebooks", "", 1, 0),
    ("Rodar os notebooks", "", 2, 2),
    ("Rodar os notebooks", "tjmt", 0, 0),
    ("Rodar os notebooks", "tjmt", 1, 1),
    ("Rodar o teste release dos tribunais do alvo", "tjmt", 0, 0),
    ("Rodar o teste release dos tribunais do alvo", "tjmt", 1, 1),
    ("Rodar o teste release dos tribunais do alvo", "tjmt", 2, 2),
    ("Rodar o teste release dos tribunais do alvo", "tjmt", 5, 0),
]


@pytest.mark.parametrize("caso", CODIGOS, ids=lambda caso: f"{caso[0]}-{caso[1] or 'completa'}-{caso[2]}")
def test_codigo_de_saida_de_cada_passo(tmp_path, uv_falso, caso):
    passo, tribunal, codigo_pytest, esperado = caso
    codigo, _, log = rodar(
        bloco_run("integration.yml", passo), tmp_path, TRIBUNAL=tribunal, CODIGO_UV=str(codigo_pytest),
        ALVO="tests/tjmt", IGNORAR="", SELECAO="tjmt or tjsc", **uv_falso,
    )

    assert codigo == esperado, log


def test_release_roda_so_os_tribunais_do_alvo(tmp_path, uv_falso):
    codigo, _, log = rodar(
        bloco_run("integration.yml", "Rodar o teste release dos tribunais do alvo"), tmp_path,
        SELECAO="tjmt or tjsc", **uv_falso,
    )

    assert codigo == 0, log
    argumentos = Path(uv_falso["ARGS_UV"]).read_text(encoding="utf-8")
    assert "tests/test_release_date_filter.py" in argumentos
    assert "-k tjmt or tjsc" in argumentos


def git(pasta, *argumentos):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *argumentos], cwd=pasta, check=True, capture_output=True,
    )


def checkout_de_pr(pasta, mudanca):
    """Monta base, ramo e o commit de merge do PR; ``mudanca`` altera a árvore no ramo."""
    pasta.mkdir(parents=True, exist_ok=True)
    git(pasta, "init", "-q", "-b", "main")
    for caminho in ("src/juscraper/utils/x.py", "CHANGELOG.md", "README.md"):
        (pasta / caminho).parent.mkdir(parents=True, exist_ok=True)
        (pasta / caminho).write_text(f"{caminho}\n" * 20, encoding="utf-8")
    git(pasta, "add", "-A")
    git(pasta, "commit", "-qm", "base")
    git(pasta, "switch", "-qc", "ramo")
    mudanca(pasta)
    git(pasta, "add", "-A")
    git(pasta, "commit", "-qm", "ramo")
    git(pasta, "switch", "-q", "main")
    # A base anda depois do ramo, como no PR real: o diff contra o primeiro
    # pai do merge não pode trazer a mudança da base.
    (pasta / "src/juscraper/core/base.py").parent.mkdir(parents=True, exist_ok=True)
    (pasta / "src/juscraper/core/base.py").write_text("base andou\n", encoding="utf-8")
    git(pasta, "add", "-A")
    git(pasta, "commit", "-qm", "base andou")
    git(pasta, "merge", "-q", "--no-ff", "ramo", "-m", "merge")
    return pasta


def acrescentar(caminho):
    def mudar(pasta):
        with (pasta / caminho).open("a", encoding="utf-8") as arquivo:
            arquivo.write("mudou\n")
    return mudar


def mover(origem, destino):
    def mudar(pasta):
        (pasta / destino).parent.mkdir(parents=True, exist_ok=True)
        git(pasta, "mv", origem, destino)
    return mudar


def junto(*mudancas):
    def mudar(pasta):
        for mudanca in mudancas:
            mudanca(pasta)
    return mudar


@pytest.mark.parametrize(
    ("mudanca", "dispensado", "esperado"),
    [
        (acrescentar("README.md"), "false", 0),
        (acrescentar("src/juscraper/utils/x.py"), "false", 1),
        (acrescentar("src/juscraper/utils/x.py"), "true", 0),
        (junto(acrescentar("src/juscraper/utils/x.py"), acrescentar("CHANGELOG.md")), "false", 0),
        # Remover código público movendo-o para fora de src/ também pede entrada.
        (mover("src/juscraper/utils/x.py", "scripts/x.py"), "false", 1),
    ],
    ids=["sem-src", "src-sem-entrada", "src-com-etiqueta", "src-com-entrada", "src-movido-para-fora"],
)
def test_changelog(tmp_path, mudanca, dispensado, esperado):
    pasta = checkout_de_pr(tmp_path / "repo", mudanca)

    codigo, _, log = rodar(bloco_run("changelog.yml", "Conferir a entrada no CHANGELOG"), pasta, DISPENSADO=dispensado)

    assert codigo == esperado, log
    if esperado:
        assert "::error title=Falta entrada no CHANGELOG::" in log


@pytest.mark.parametrize(
    ("tribunal", "suite", "fora"),
    [
        # A execução dirigida roda o teste release e ignora FORA_DO_CI.
        ("tjmt", "release", None),
        # A completa roda os notebooks e diz quem ficou fora, para que a falta
        # de falhas não se leia como tribunal em dia.
        ("", "notebooks", "`tjpb`, `tjrs`"),
    ],
    ids=["dirigida", "completa"],
)
def test_relatorio_traz_as_suites_e_quem_ficou_fora(tmp_path, tribunal, suite, fora):
    (tmp_path / "scripts").mkdir()
    shutil.copy(RAIZ / "scripts" / "integration_report.py", tmp_path / "scripts")
    junit = '<testsuites><testsuite><testcase classname="tests.tjmt.t" name="x"/></testsuite></testsuites>'
    for nome in ("integracao", suite):
        (tmp_path / f"junit-{nome}.xml").write_text(junit, encoding="utf-8")
    resumo = tmp_path / "resumo.md"

    codigo, _, log = rodar(
        bloco_run("integration.yml", "Montar o relatório"), tmp_path, TRIBUNAL=tribunal,
        FORA_DO_CI="tjrs tjpb", EXECUCAO="https://example.invalid/1",
        GITHUB_STEP_SUMMARY=str(resumo),
    )

    assert codigo == 0, log
    corpo = resumo.read_text(encoding="utf-8")
    assert f"| {suite} | 1 | 0 | 0 |" in corpo
    # Execução dirigida sem notebook não lista a suíte de notebooks.
    assert ("| notebooks |" in corpo) == (suite == "notebooks")
    assert ("Fora desta execução" in corpo) == (fora is not None)
    if fora is not None:
        assert fora in corpo


@pytest.mark.parametrize(
    ("resultado", "resultado_piso", "esperado"),
    [
        ("success", "success", 0),
        ("success", "failure", 1),
        ("failure", "success", 1),
    ],
    ids=["tudo-verde", "piso-falhou", "matriz-falhou"],
)
def test_testes_obrigatorios_exigem_a_matriz_e_o_piso_do_pandas(tmp_path, resultado, resultado_piso, esperado):
    codigo, _, log = rodar(
        bloco_run("tests.yml", "Conferir o resultado de todas as pernas"), tmp_path,
        RESULTADO=resultado, RESULTADO_PISO=resultado_piso,
    )

    assert codigo == esperado, log
