"""``-k <tribunal>`` em ``tests/test_release_date_filter.py`` seleciona só os casos do tribunal.

Coleta offline (``--collect-only``): nenhum teste de release roda aqui. Antes,
``-k stm`` selecionava a matriz inteira, porque "stm" casa com o atributo
``pytestmark`` que ``@pytest.mark.parametrize`` grava na função de teste.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
ARQUIVO = "tests/test_release_date_filter.py"
TESTES = ("test_filtro_data_unica", "test_paginacao_com_data_unica", "test_fim_da_janela_sem_dia_seguinte")


def _coletados(*selecao: str) -> list[str]:
    """Casos coletados, como ``teste[tribunal]``, num pytest à parte e sem o ``addopts`` do repositório."""
    ambiente = {nome: valor for nome, valor in os.environ.items() if nome != "PYTEST_ADDOPTS"}
    comando = [sys.executable, "-m", "pytest", ARQUIVO, "-o", "addopts=", "-m", "release", *selecao,
               "--collect-only", "-q", "-p", "no:cacheprovider"]
    resultado = subprocess.run(
        comando, cwd=RAIZ, env=ambiente, capture_output=True, text=True, check=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    return [linha.split("::")[-1] for linha in resultado.stdout.splitlines() if "::" in linha]


@pytest.mark.parametrize("tribunal", ["stm", "tjsp", "tjrs"])
def test_k_seleciona_so_os_casos_do_tribunal(tribunal):
    assert sorted(_coletados("-k", tribunal)) == sorted(f"{teste}[{tribunal}]" for teste in TESTES)


def test_sem_k_a_matriz_inteira_continua_coletada():
    casos = _coletados()
    tribunais = {caso.split("[")[1].rstrip("]") for caso in casos}

    assert {"stm", "tjsp", "tjrs"} < tribunais
    assert len(casos) == len(TESTES) * len(tribunais)
