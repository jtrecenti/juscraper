"""Exercita scripts/integration_report.py pela linha de comando, sem rede."""

import json
import re
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "integration_report.py"
EXECUCAO = "https://example.invalid/execucao/1"
FALHA_TJSP = "tests.tjsp.test_cjsg_integration::test_busca"
FALHA_TJRS = "tests.tjrs.test_cjsg::test_busca"


def gravar_junit(caminho, casos):
    """Grava um JUnit mínimo; cada caso é ``(classname, name, filhos_em_xml)``."""
    corpo = "".join(
        f"<testcase classname={quoteattr(classe)} name={quoteattr(nome)}>{filhos}</testcase>"
        for classe, nome, filhos in casos
    )
    caminho.write_text(f'<testsuites><testsuite name="pytest">{corpo}</testsuite></testsuites>', encoding="utf-8")
    return caminho


def falha(mensagem="AssertionError: coluna ausente"):
    return f"<failure message={quoteattr(mensagem)}>traceback</failure>"


def executar(*argumentos):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *argumentos], check=False, capture_output=True, text=True,
    )


def relatorio(pasta, suites, anterior=None):
    """Roda o subcomando ``relatorio`` e devolve ``(corpo, comentario)``."""
    argumentos = ["relatorio", "--execucao", EXECUCAO, "--data", "2026-10-14"]
    for rotulo, caminho in suites.items():
        argumentos += ["--suite", f"{rotulo}={caminho}"]
    if anterior is not None:
        caminho_anterior = pasta / "anterior.md"
        caminho_anterior.write_text(anterior, encoding="utf-8")
        argumentos += ["--anterior", str(caminho_anterior)]
    resultado = executar(*argumentos, "--corpo", str(pasta / "corpo.md"), "--comentario", str(pasta / "comentario.md"))
    assert resultado.returncode == 0, resultado.stderr
    return (
        (pasta / "corpo.md").read_text(encoding="utf-8"),
        (pasta / "comentario.md").read_text(encoding="utf-8"),
    )


def falhas_gravadas(corpo):
    """Lê a lista da última linha não vazia do corpo, onde o script a grava."""
    achado = re.fullmatch(r"<!-- falhas-integracao: (.*) -->", corpo.rstrip().splitlines()[-1])
    assert achado is not None, "corpo não termina na lista de falhas gravada"
    return json.loads(achado.group(1))


@pytest.mark.parametrize(
    ("data", "evento", "esperado"),
    [
        ("2026-12-19", "schedule", "rodar=true"),
        ("2026-12-20", "schedule", "rodar=false"),
        ("2026-12-31", "schedule", "rodar=false"),
        ("2027-01-01", "schedule", "rodar=false"),
        ("2027-01-20", "schedule", "rodar=false"),
        ("2027-01-21", "schedule", "rodar=true"),
        ("2026-07-01", "schedule", "rodar=true"),
        ("2026-12-25", "workflow_dispatch", "rodar=true"),
        ("2027-01-10", "pull_request", "rodar=true"),
    ],
)
def test_calendario_pausa_so_a_execucao_agendada_no_recesso(data, evento, esperado):
    resultado = executar("calendario", "--data", data, "--evento", evento)

    assert resultado.returncode == 0, resultado.stderr
    assert resultado.stdout.strip() == esperado


def test_corpo_conta_cada_caso_uma_vez_e_grava_as_falhas(tmp_path):
    junit = gravar_junit(tmp_path / "integracao.xml", [
        ("tests.tjsp.test_cjsg_integration", "test_busca", falha("AssertionError: coluna ausente\nsegunda linha")),
        ("tests.tjrs.test_cjsg", "test_busca", '<error message="ReadTimeout">traceback</error>'),
        # O pytest grava teste que falha e depois quebra no teardown como dois
        # <testcase> com o mesmo id.
        ("tests.tjto.test_cjsg", "test_teardown", falha("falhou no teste")),
        ("tests.tjto.test_cjsg", "test_teardown", '<error message="failed on teardown with RuntimeError"/>'),
        ("tests.trf3.test_cpopg_integration", "test_bloqueio", '<skipped type="pytest.xfail" message="anti-bot"/>'),
        ("tests.tjdft.test_cjsg", "test_pulado", '<skipped type="pytest.skip" message="sem token"/>'),
        ("tests.tjac.test_cjsg", "test_ok", ""),
    ])

    corpo, comentario = relatorio(tmp_path, {"integração": junit})

    assert "| integração | 1 | 3 | 2 |" in corpo
    assert "## Falhas (3)" in corpo
    assert f"| `{FALHA_TJSP}` | `AssertionError: coluna ausente` |" in corpo
    assert "segunda linha" not in corpo
    assert f"| `{FALHA_TJRS}` | `ReadTimeout` |" in corpo
    assert "| `tests.tjto.test_cjsg::test_teardown` | `falhou no teste` |" in corpo
    assert falhas_gravadas(corpo) == [FALHA_TJRS, FALHA_TJSP, "tests.tjto.test_cjsg::test_teardown"]
    assert "14/10/2026" in corpo
    assert EXECUCAO in corpo
    assert comentario == ""


def test_primeira_execucao_nao_comenta_mesmo_com_falha(tmp_path):
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg_integration", "test_busca", falha())])

    _, sem_arquivo = relatorio(tmp_path, {"integração": junit})
    _, arquivo_vazio = relatorio(tmp_path, {"integração": junit}, anterior="\n")

    assert sem_arquivo == ""
    assert arquivo_vazio == ""


def test_lista_igual_nao_comenta(tmp_path):
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg_integration", "test_busca", falha())])
    corpo_anterior, _ = relatorio(tmp_path, {"integração": junit})

    _, comentario = relatorio(tmp_path, {"integração": junit}, anterior=corpo_anterior)

    assert comentario == ""


def test_lista_diferente_comenta_o_que_entrou_e_o_que_saiu(tmp_path):
    antes = gravar_junit(tmp_path / "antes.xml", [
        ("tests.tjsp.test_cjsg_integration", "test_busca", falha()),
        ("tests.tjac.test_cjsg", "test_ok", falha()),
    ])
    corpo_anterior, _ = relatorio(tmp_path, {"integração": antes})
    depois = gravar_junit(tmp_path / "depois.xml", [
        ("tests.tjsp.test_cjsg_integration", "test_busca", falha()),
        ("tests.tjrs.test_cjsg", "test_busca", falha()),
        ("tests.tjac.test_cjsg", "test_ok", ""),
    ])

    _, comentario = relatorio(tmp_path, {"integração": depois}, anterior=corpo_anterior)

    entrou, saiu = comentario.split("Saíram da lista de falhas:")
    assert "Passaram a falhar:" in entrou
    assert f"- `{FALHA_TJRS}`" in entrou
    assert "- `tests.tjac.test_cjsg::test_ok`" in saiu
    assert FALHA_TJSP not in comentario


def test_tudo_verde_depois_de_falha_comenta_so_a_saida(tmp_path):
    antes = gravar_junit(tmp_path / "antes.xml", [("tests.tjsp.test_cjsg_integration", "test_busca", falha())])
    corpo_anterior, _ = relatorio(tmp_path, {"integração": antes})
    depois = gravar_junit(tmp_path / "depois.xml", [("tests.tjsp.test_cjsg_integration", "test_busca", "")])

    corpo, comentario = relatorio(tmp_path, {"integração": depois}, anterior=corpo_anterior)

    assert "Nenhuma falha nesta execução." in corpo
    assert falhas_gravadas(corpo) == []
    assert "Passaram a falhar" not in comentario
    assert f"- `{FALHA_TJSP}`" in comentario


@pytest.mark.parametrize(
    "anterior",
    [
        "corpo reescrito à mão, sem a lista",
        '<!-- falhas-integracao: ["a", -->',
        '<!-- falhas-integracao: {"a": 1} -->',
    ],
)
def test_corpo_anterior_sem_lista_valida_trata_toda_falha_como_nova(tmp_path, anterior):
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg_integration", "test_busca", falha())])

    _, comentario = relatorio(tmp_path, {"integração": junit}, anterior=anterior)

    assert f"- `{FALHA_TJSP}`" in comentario
    assert "Saíram da lista de falhas" not in comentario


def test_suite_sem_junit_entra_como_nao_terminada(tmp_path):
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjac.test_cjsg", "test_ok", "")])
    suites = {"integração": junit, "notebooks": tmp_path / "ausente.xml"}
    corpo_anterior, _ = relatorio(tmp_path, {"integração": junit})

    corpo, comentario = relatorio(tmp_path, suites, anterior=corpo_anterior)

    assert "| notebooks | não terminou | | |" in corpo
    assert falhas_gravadas(corpo) == ["notebooks: a suíte não terminou"]
    assert "- `notebooks: a suíte não terminou`" in comentario


def test_id_com_fecho_de_comentario_e_barra_nao_corrompe_o_corpo(tmp_path):
    nome = "test_filtro[a-->b|c]"
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg", nome, falha("erro | com barra"))])

    corpo, _ = relatorio(tmp_path, {"integração": junit})
    _, comentario = relatorio(tmp_path, {"integração": junit}, anterior=corpo)

    assert falhas_gravadas(corpo) == [f"tests.tjsp.test_cjsg::{nome}"]
    assert "| `tests.tjsp.test_cjsg::test_filtro[a-->b\\|c]` | `erro \\| com barra` |" in corpo
    assert comentario == ""


def test_tabela_e_cortada_mas_a_lista_gravada_fica_inteira(tmp_path):
    total = 130
    junit = gravar_junit(
        tmp_path / "integracao.xml",
        [("tests.tjsp.test_cjsg", f"test_{numero:03d}", falha("x" * 500)) for numero in range(total)],
    )

    corpo, _ = relatorio(tmp_path, {"integração": junit})

    linhas_de_falha = [linha for linha in corpo.splitlines() if linha.startswith("| `tests.tjsp")]
    assert len(linhas_de_falha) == 100
    assert "Outras 30 falhas estão no registro da execução." in corpo
    assert len(falhas_gravadas(corpo)) == total
    assert f"| `tests.tjsp.test_cjsg::test_000` | `{'x' * 160}` |" in linhas_de_falha


@pytest.mark.parametrize(
    "mensagem",
    [
        "<!-- falhas-integracao: [] -->",
        "<!-- falhas-integracao: ",
        'resposta do portal: <!-- falhas-integracao: ["outro"] --> fim',
    ],
)
def test_mensagem_que_imita_o_marcador_nao_vira_a_lista_anterior(tmp_path, mensagem):
    caso = ("tests.tjsp.test_cjsg_integration", "test_busca", falha(mensagem))
    junit = gravar_junit(tmp_path / "integracao.xml", [caso])
    corpo, _ = relatorio(tmp_path, {"integração": junit})

    _, comentario = relatorio(tmp_path, {"integração": junit}, anterior=corpo)

    assert falhas_gravadas(corpo) == [FALHA_TJSP]
    assert comentario == ""


def test_id_que_imita_o_marcador_nao_corrompe_a_lista(tmp_path):
    nome = 'test_x[<!-- falhas-integracao: ["falso"] -->]'
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg", nome, falha())])
    corpo, _ = relatorio(tmp_path, {"integração": junit})

    _, comentario = relatorio(tmp_path, {"integração": junit}, anterior=corpo)

    assert falhas_gravadas(corpo) == [f"tests.tjsp.test_cjsg::{nome}"]
    assert comentario == ""


def test_texto_do_tribunal_fica_em_trecho_de_codigo(tmp_path):
    mensagem = "erro @alguem <img src=x> `crase` [link](http://example.invalid) #12"
    caso = ("tests.tjsp.test_cjsg_integration", "test_busca", falha(mensagem))
    junit = gravar_junit(tmp_path / "integracao.xml", [caso])

    corpo, _ = relatorio(tmp_path, {"integração": junit})

    assert f"| `{FALHA_TJSP}` | `erro @alguem <img src=x> 'crase' [link](http://example.invalid) #12` |" in corpo


# Forma da mensagem gravada pelo nbmake 1.5.5 no JUnit do pytest 9.1: o
# traceback da célula, com cores ANSI cujo ESC o pytest troca por `#x1B`.
MENSAGEM_NBMAKE = (
    "---------------------------------------------------------------------------\n"
    "raise ValueError('portal fora')\n"
    "#x1B[31m---------------------------------------------------------------------------#x1B[39m\n"
    "#x1B[31mValueError#x1B[39m                                Traceback (most recent call last)\n"
    "#x1B[36mCell#x1B[39m#x1B[36m #x1B[39m#x1B[32mIn[1]#x1B[39m#x1B[32m, line 1#x1B[39m\n"
    "#x1B[32m----> #x1B[39m#x1B[32m1#x1B[39m #x1B[38;5;28;01mraise#x1B[39;00m "
    "ValueError(#x1B[33m'portal fora'#x1B[39m)\n"
    "\n"
    "#x1B[31mValueError#x1B[39m: portal fora"
)


@pytest.mark.parametrize(
    ("mensagem", "esperado"),
    [
        (MENSAGEM_NBMAKE, "ValueError: portal fora"),
        ("-" * 75 + "\n\nRuntimeError: kernel morreu", "RuntimeError: kernel morreu"),
        (
            "A cell timed out while it was being executed, after 300 seconds.\n"
            "The message was: Cell execution timed out.",
            "A cell timed out while it was being executed, after 300 seconds.",
        ),
    ],
)
def test_mensagem_do_notebook_mostra_a_excecao(tmp_path, mensagem, esperado):
    junit = gravar_junit(tmp_path / "notebooks.xml", [("docs.notebooks.tjsp.ipynb", "tjsp.ipynb", falha(mensagem))])

    corpo, _ = relatorio(tmp_path, {"notebooks": junit})

    assert f"| `docs.notebooks.tjsp.ipynb::tjsp.ipynb` | `{esperado}` |" in corpo


def test_barra_vertical_so_tem_escape_na_tabela(tmp_path):
    antes = gravar_junit(tmp_path / "antes.xml", [("tests.tjsp.test_cjsg", "test_x", "")])
    corpo_anterior, _ = relatorio(tmp_path, {"integração": antes})
    depois = gravar_junit(tmp_path / "depois.xml", [("tests.tjsp.test_cjsg", "test_x[a|b]", falha())])

    corpo, comentario = relatorio(tmp_path, {"integração": depois}, anterior=corpo_anterior)

    assert "| `tests.tjsp.test_cjsg::test_x[a\\|b]` |" in corpo
    assert "- `tests.tjsp.test_cjsg::test_x[a|b]`" in comentario


def test_corpo_lista_quem_ficou_fora_da_execucao(tmp_path):
    junit = gravar_junit(tmp_path / "integracao.xml", [("tests.tjsp.test_cjsg", "test_ok", "")])
    argumentos = [
        "relatorio", "--suite", f"integração={junit}", "--execucao", EXECUCAO, "--data", "2026-10-14",
        "--corpo", str(tmp_path / "corpo.md"), "--comentario", str(tmp_path / "comentario.md"),
    ]

    resultado = executar(*argumentos, "--fora", "tjrs tjam")
    sem_lista = executar(*argumentos[:-4], "--corpo", str(tmp_path / "sem.md"), "--comentario", str(tmp_path / "c2.md"))

    assert resultado.returncode == 0, resultado.stderr
    assert sem_lista.returncode == 0, sem_lista.stderr
    corpo = (tmp_path / "corpo.md").read_text(encoding="utf-8")
    assert "Fora desta execução, porque dão problema só no runner do GitHub: `tjam`, `tjrs`." in corpo
    assert "Fora desta execução" not in (tmp_path / "sem.md").read_text(encoding="utf-8")
