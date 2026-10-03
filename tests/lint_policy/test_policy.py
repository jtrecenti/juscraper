"""Exercita o gate com Git e Ruff reais em repositórios temporários, sem rede."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CODIGO_ANTIGO = '"""Módulo de exemplo."""\n\ndef obter_numero():\n    """Retorna o número."""\n    return 1\n'
CODIGO_CORRIGIDO = CODIGO_ANTIGO.replace("obter_numero():", "obter_numero() -> int:")


def git(raiz, *argumentos):
    return subprocess.run(
        ["git", *argumentos], cwd=raiz, check=True, capture_output=True, text=True,
    ).stdout.strip()


def gravar_excecoes(raiz, excecoes):
    linhas = ['extend = "pyproject.toml"', "[lint.extend-per-file-ignores]"]
    linhas.extend(f"{json.dumps(caminho)} = {json.dumps(regras)}" for caminho, regras in excecoes.items())
    (raiz / "ruff.toml").write_text("\n".join(linhas) + "\n", encoding="utf-8")


def executar_gate(raiz, *argumentos):
    return subprocess.run(
        [sys.executable, str(raiz / "scripts/check_lint_policy.py"), *argumentos],
        cwd=raiz, check=False, capture_output=True, text=True,
    )


def executar_ruff(raiz, *argumentos):
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", *argumentos],
        cwd=raiz, check=False, capture_output=True, text=True,
    )


def registrar_base(raiz):
    git(raiz, "add", ".")
    git(raiz, "-c", "user.name=Teste", "-c", "user.email=teste@example.com",
        "-c", "commit.gpgsign=false", "commit", "-qm", "Base de teste")
    git(raiz, "update-ref", "refs/remotes/origin/main", "HEAD")


@pytest.fixture
def repositorio(tmp_path):
    for diretorio in ("src", "tests", "scripts"):
        (tmp_path / diretorio).mkdir()
    shutil.copyfile(RAIZ / "pyproject.toml", tmp_path / "pyproject.toml")
    shutil.copyfile(RAIZ / "scripts/check_lint_policy.py", tmp_path / "scripts/check_lint_policy.py")
    (tmp_path / "src/antigo.py").write_text(CODIGO_ANTIGO, encoding="utf-8")
    (tmp_path / "tests/__init__.py").touch()
    gravar_excecoes(tmp_path, {"src/antigo.py": ["ANN201"]})
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "core.hooksPath", "/dev/null")
    registrar_base(tmp_path)
    return tmp_path


def test_codigo_antigo_passa_com_a_dispensa_existente(repositorio):
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr
    assert "nenhuma dispensa nova ou obsoleta" in resultado.stdout
    assert executar_ruff(repositorio, "src", "tests").returncode == 0


def test_correcao_com_remocao_da_dispensa_passa(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_CORRIGIDO, encoding="utf-8")
    gravar_excecoes(repositorio, {})
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_correcao_exige_retirar_dispensa_obsoleta(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_CORRIGIDO, encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Remova a dispensa obsoleta: src/antigo.py: ANN201" in resultado.stderr


def test_arquivo_excluido_exige_retirar_dispensa(repositorio):
    (repositorio / "src/antigo.py").unlink()
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "dispensa obsoleta: src/antigo.py: ANN201" in resultado.stderr


def test_nova_ocorrencia_da_regra_dispensada_no_mesmo_arquivo_passa(repositorio):
    caminho = repositorio / "src/antigo.py"
    caminho.write_text(CODIGO_ANTIGO + '\ndef outro_numero():\n    """Retorna outro número."""\n    return 2\n')
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_arquivo_novo_nao_herda_dispensa(repositorio):
    (repositorio / "src/novo.py").write_text(CODIGO_ANTIGO, encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "src/novo.py:3: ANN201" in resultado.stderr
    assert executar_ruff(repositorio, "src", "tests").returncode == 1


def test_regra_diferente_no_arquivo_antigo_falha(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_ANTIGO + '\nprint("novo problema")\n', encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "T201" in resultado.stderr


def test_nao_permite_acrescentar_regra_a_arquivo_dispensado(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_ANTIGO + '\nprint("problema")\n', encoding="utf-8")
    gravar_excecoes(repositorio, {"src/antigo.py": ["ANN201", "T201"]})
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Nova dispensa proibida: src/antigo.py: T201" in resultado.stderr


def test_nao_permite_trocar_dispensa_entre_arquivos(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_CORRIGIDO, encoding="utf-8")
    (repositorio / "src/novo.py").write_text(CODIGO_ANTIGO, encoding="utf-8")
    gravar_excecoes(repositorio, {"src/novo.py": ["ANN201"]})
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Nova dispensa proibida: src/novo.py: ANN201" in resultado.stderr


def test_base_inexistente_falha_sem_ignorar_comparacao(repositorio):
    resultado = executar_gate(repositorio, "--base-ref", "referencia-inexistente")
    assert resultado.returncode == 1
    assert "Falha ao consultar a base Git" in resultado.stderr


def test_dispensa_retirada_da_base_nao_pode_voltar(repositorio):
    (repositorio / "src/antigo.py").write_text(CODIGO_CORRIGIDO, encoding="utf-8")
    gravar_excecoes(repositorio, {})
    registrar_base(repositorio)
    (repositorio / "src/antigo.py").write_text(CODIGO_ANTIGO, encoding="utf-8")
    gravar_excecoes(repositorio, {"src/antigo.py": ["ANN201"]})
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Nova dispensa proibida: src/antigo.py: ANN201" in resultado.stderr


def test_comparacao_usa_ancestral_comum_quando_main_avanca(repositorio):
    origem = git(repositorio, "rev-parse", "HEAD")
    (repositorio / "src/antigo.py").write_text(CODIGO_CORRIGIDO, encoding="utf-8")
    gravar_excecoes(repositorio, {})
    registrar_base(repositorio)
    git(repositorio, "checkout", "--detach", origem)
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_referencia_explicita_funciona_sem_origin_main(repositorio):
    origem = git(repositorio, "rev-parse", "HEAD")
    git(repositorio, "update-ref", "-d", "refs/remotes/origin/main")
    resultado = executar_gate(repositorio, "--base-ref", origem)
    assert resultado.returncode == 0, resultado.stderr


@pytest.mark.parametrize("excecoes", [
    {"src/*.py": ["ANN201"]},
    {"src/antigo.py": ["ANN"]},
    {"src/../src/antigo.py": ["ANN201"]},
    {"src/antigo.py": ["ANN201", "ANN201"]},
    {"src/antigo.py": []},
])
def test_rejeita_dispensa_ampla_ou_malformada(repositorio, excecoes):
    gravar_excecoes(repositorio, excecoes)
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Política de lint inválida" in resultado.stderr


def test_rejeita_configuracao_extra_no_arquivo_de_dispensas(repositorio):
    with (repositorio / "ruff.toml").open("a", encoding="utf-8") as arquivo:
        arquivo.write('\n[lint]\nignore = ["T201"]\n')
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "Política de lint inválida" in resultado.stderr


@pytest.fixture
def primeira_adocao(repositorio):
    (repositorio / "ruff.toml").unlink()
    registrar_base(repositorio)
    gravar_excecoes(repositorio, {"src/antigo.py": ["ANN201"]})
    return repositorio


def test_primeira_adocao_mede_a_base_sem_lista_anterior(primeira_adocao):
    resultado = executar_gate(primeira_adocao)
    assert resultado.returncode == 0, resultado.stderr


def test_primeira_adocao_nao_autoriza_arquivo_novo(primeira_adocao):
    (primeira_adocao / "src/novo.py").write_text(CODIGO_ANTIGO, encoding="utf-8")
    gravar_excecoes(primeira_adocao, {"src/antigo.py": ["ANN201"], "src/novo.py": ["ANN201"]})
    resultado = executar_gate(primeira_adocao)
    assert resultado.returncode == 1
    assert "Nova dispensa proibida: src/novo.py: ANN201" in resultado.stderr


def test_primeira_adocao_nao_autoriza_regra_nova(primeira_adocao):
    (primeira_adocao / "src/antigo.py").write_text(CODIGO_ANTIGO + '\nprint("problema")\n', encoding="utf-8")
    gravar_excecoes(primeira_adocao, {"src/antigo.py": ["ANN201", "T201"]})
    resultado = executar_gate(primeira_adocao)
    assert resultado.returncode == 1
    assert "Nova dispensa proibida: src/antigo.py: T201" in resultado.stderr


def test_politica_de_testes_dispensa_anotacao_docstring_e_assert(repositorio):
    (repositorio / "tests/test_novo.py").write_text('def test_numero():\n    assert True\n', encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr


def test_politica_de_src_continua_exigindo_anotacao_docstring_e_seguranca(repositorio):
    (repositorio / "src/novo.py").write_text('def obter():\n    assert True\n    return 1\n', encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    for regra in ("ANN201", "D100", "D103", "S101"):
        assert regra in resultado.stderr


def test_docstring_existente_em_teste_continua_sujeita_ao_formato(repositorio):
    (repositorio / "tests/test_novo.py").write_text('def test_numero():\n    """Sem ponto"""\n    assert True\n')
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "D415" in resultado.stderr


def test_samples_ficam_fora_mesmo_quando_passados_explicitamente(repositorio):
    amostra = repositorio / "tests/tribunal/samples/invalido.py"
    amostra.parent.mkdir(parents=True)
    amostra.write_text("isto não é Python válido", encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 0, resultado.stderr
    assert executar_ruff(repositorio, str(amostra)).returncode == 0


def test_erro_de_sintaxe_nao_pode_passar_como_codigo_limpo(repositorio):
    (repositorio / "src/novo.py").write_text("def quebrado(\n", encoding="utf-8")
    resultado = executar_gate(repositorio)
    assert resultado.returncode == 1
    assert "invalid-syntax" in resultado.stderr
