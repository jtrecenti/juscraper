"""Contratos dos helpers mínimos usados pelos testes de scripts e gates."""

import subprocess

import pytest

from tests._tooling import carregar_script, git_saida


def test_carregar_script_isola_nome_sem_executar_main(tmp_path):
    marcador = tmp_path / "main_executado"
    codigo = (
        "VALOR = 7\n"
        "if __name__ == '__main__':\n"
        f"    open({str(marcador)!r}, 'w').write('erro')\n"
    )
    primeiro = tmp_path / "primeiro.py"
    segundo = tmp_path / "segundo.py"
    primeiro.write_text(codigo, encoding="utf-8")
    segundo.write_text(codigo, encoding="utf-8")

    um = carregar_script("script_um", primeiro)
    dois = carregar_script("script_dois", segundo)

    assert (um.__name__, dois.__name__) == ("script_um", "script_dois")
    assert um is not dois
    assert (um.VALOR, dois.VALOR) == (7, 7)
    assert not marcador.exists()


def test_git_saida_sucesso_e_falha_em_repositorio_temporario(tmp_path):
    assert git_saida(tmp_path, "init", "-q") == ""
    assert git_saida(tmp_path, "rev-parse", "--is-inside-work-tree") == "true"

    with pytest.raises(subprocess.CalledProcessError):
        git_saida(tmp_path, "rev-parse", "--verify", "refs/heads/inexistente")
