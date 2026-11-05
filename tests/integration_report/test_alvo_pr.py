"""Exercita o subcomando ``alvo-pr`` de scripts/integration_report.py, sem rede."""

import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "integration_report.py"
WORKFLOW = RAIZ / ".github" / "workflows" / "integration.yml"


def alvo(raiz, arquivos, fora="", pasta=None):
    """Roda ``alvo-pr`` e devolve ``(a rodar, fora do CI)`` como listas."""
    lista = (pasta or raiz) / "arquivos.txt"
    lista.write_text("\n".join(arquivos) + "\n", encoding="utf-8")
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT), "alvo-pr", "--arquivos", str(lista), "--fora", fora, "--raiz", str(raiz)],
        check=False, capture_output=True, text=True,
    )
    assert resultado.returncode == 0, resultado.stderr
    saida = dict(linha.split("=", 1) for linha in resultado.stdout.splitlines())
    return saida["tribunais"].split(), saida["fora"].split()


def criar(raiz, caminho, texto=""):
    arquivo = raiz / caminho
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(texto, encoding="utf-8")


@pytest.fixture
def arvore(tmp_path):
    """Árvore mínima com dois tribunais e-SAJ, um TRF, agregadores e uma família de agregador."""
    criar(tmp_path, "src/juscraper/courts/_esaj/busca.py", "class EsajSearchScraper: ...\n")
    criar(tmp_path, "src/juscraper/courts/_trf/consulta.py", "class TRFConsultaScraper: ...\n")
    criar(tmp_path, "src/juscraper/courts/tjsp/client.py", "from .._esaj.busca import EsajSearchScraper\n")
    criar(
        tmp_path, "src/juscraper/courts/tjac/client.py", "from juscraper.courts._esaj.busca import EsajSearchScraper\n",
    )
    # Cita a família só em comentário, sem o ponto de módulo: não importa.
    criar(tmp_path, "src/juscraper/courts/tjmt/client.py", "# não usa o _esaj\n")
    criar(tmp_path, "src/juscraper/courts/trf5/client.py", "from .._trf.consulta import TRFConsultaScraper\n")
    criar(tmp_path, "src/juscraper/courts/__init__.py")
    criar(tmp_path, "src/juscraper/aggregators/_pdpj_sso/sso.py")
    criar(tmp_path, "src/juscraper/aggregators/jusbr/client.py", "from .._pdpj_sso.sso import PdpjSsoMixin\n")
    criar(tmp_path, "src/juscraper/aggregators/datajud/client.py")
    for nome in ("tjsp", "tjac", "tjmt", "trf5", "jusbr", "pdpj_sso", "datajud", "core", "utils"):
        criar(tmp_path, f"tests/{nome}/test_x.py")
    return tmp_path


@pytest.mark.parametrize(
    ("arquivos", "esperado"),
    [
        (["src/juscraper/courts/tjmt/client.py"], ["tjmt"]),
        (["tests/tjmt/samples/cjsg.json"], ["tjmt"]),
        (["docs/notebooks/tjmt.ipynb"], ["tjmt"]),
        (["src/juscraper/aggregators/datajud/client.py"], ["datajud"]),
        # A família conta para quem a importa, e não para quem só a cita.
        (["src/juscraper/courts/_esaj/busca.py"], ["tjac", "tjsp"]),
        (["src/juscraper/courts/_trf/consulta.py"], ["trf5"]),
        # A família de agregador tem diretório de teste próprio, que também roda.
        (["src/juscraper/aggregators/_pdpj_sso/sso.py"], ["jusbr", "pdpj_sso"]),
        (["src/juscraper/courts/tjmt/client.py", "tests/tjsp/test_x.py"], ["tjmt", "tjsp"]),
    ],
)
def test_alvo_e_o_tribunal_cujo_diretorio_o_pr_tocou(arvore, arquivos, esperado):
    assert alvo(arvore, arquivos) == (esperado, [])


@pytest.mark.parametrize(
    "arquivos",
    [
        ["src/juscraper/core/http.py"],
        ["src/juscraper/courts/__init__.py"],
        ["tests/core/test_x.py", "tests/utils/test_x.py"],
        ["tests/test_release_date_filter.py", "tests/helpers.py"],
        ["docs/notebooks/README.md", "CHANGELOG.md"],
        # Diretório novo sem teste não é tribunal que o workflow saiba rodar.
        ["src/juscraper/courts/tjzz/client.py"],
    ],
)
def test_codigo_comum_nao_aponta_tribunal(arvore, arquivos):
    assert alvo(arvore, arquivos) == ([], [])


def test_tribunal_fora_do_ci_vai_para_a_lista_de_fora(arvore):
    arquivos = ["src/juscraper/courts/_esaj/busca.py", "docs/notebooks/tjmt.ipynb"]

    assert alvo(arvore, arquivos, fora="tjac tjrs") == (["tjmt", "tjsp"], ["tjac"])


@pytest.mark.parametrize("arquivo", [".github/workflows/integration.yml", "scripts/integration_report.py"])
def test_pr_so_do_workflow_roda_o_autoteste(arvore, arquivo):
    criar(arvore, "tests/tjmg/test_x.py")
    criar(arvore, "src/juscraper/courts/tjmg/client.py")

    assert alvo(arvore, [arquivo]) == (["tjmg"], [])
    # Com tribunal tocado, o próprio tribunal já exercita o workflow.
    assert alvo(arvore, [arquivo, "tests/tjmt/test_x.py"]) == (["tjmt"], [])


def test_nome_que_nao_e_diretorio_simples_nao_passa(arvore):
    criar(arvore, "src/juscraper/courts/tj-x/client.py")
    criar(arvore, "tests/tj-x/test_x.py")

    assert alvo(arvore, ["src/juscraper/courts/tj-x/client.py", "tests/tj-x/test_x.py"]) == ([], [])


def test_todo_notebook_e_todo_tribunal_do_repositorio_tem_alvo(tmp_path):
    """Notebook ou tribunal novo sem diretório em tests/ passaria em PR sem rodar."""
    notebooks = sorted(caminho.stem for caminho in (RAIZ / "docs" / "notebooks").glob("*.ipynb"))
    tribunais = sorted(
        caminho.name
        for fonte in ("courts", "aggregators")
        for caminho in (RAIZ / "src" / "juscraper" / fonte).iterdir()
        if caminho.is_dir() and not caminho.name.startswith("_")
    )

    for nome in notebooks + tribunais:
        assert alvo(RAIZ, [f"docs/notebooks/{nome}.ipynb", f"tests/{nome}/x.py"], pasta=tmp_path) == ([nome], []), nome


def test_familias_reais_apontam_seus_tribunais(tmp_path):
    esaj, _ = alvo(RAIZ, ["src/juscraper/courts/_esaj/x.py"], pasta=tmp_path)
    trf, _ = alvo(RAIZ, ["src/juscraper/courts/_trf/x.py"], pasta=tmp_path)

    assert {"tjsp", "tjal", "tjce"} <= set(esaj)
    assert {"trf1", "trf3", "trf5"} <= set(trf)


def test_workflow_passa_a_lista_fora_do_ci_ao_alvo_do_pr():
    texto = WORKFLOW.read_text(encoding="utf-8")

    assert 'alvo-pr --arquivos arquivos.txt --fora "$FORA_DO_CI"' in texto
    assert "git diff --no-renames --name-only HEAD^1 HEAD > arquivos.txt" in texto
