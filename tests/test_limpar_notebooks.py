r"""Testa ``scripts/limpar_notebooks.py``, que tira o ruído de execução sem apagar outputs.

As saídas de stream reproduzem o que ``jupyter nbconvert --execute`` gravou no
``docs/notebooks/tjsc.ipynb``: um stream por atualização do tqdm, cada um com
``\r`` no início, e o ``\n`` de fechamento num stream à parte.
"""

import json
from pathlib import Path

from tests._tooling import carregar_script

RAIZ = Path(__file__).resolve().parents[1]
limpar_notebooks = carregar_script("limpar_notebooks", RAIZ / "scripts" / "limpar_notebooks.py")

CARIMBOS = {
    "iopub.execute_input": "2026-11-15T12:25:53.689788Z",
    "iopub.status.busy": "2026-11-15T12:25:53.688618Z",
    "iopub.status.idle": "2026-11-15T12:25:55.824725Z",
    "shell.execute_reply": "2026-11-15T12:25:55.823763Z",
}
METADATA_NOTEBOOK = {
    "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    "language_info": {"name": "python", "version": "3.13.5"},
}
TABELA = {"data": {"text/plain": ["   processo\n", "0  5000001\n"]}, "execution_count": 2, "metadata": {},
          "output_type": "execute_result"}


def _stream(nome, *linhas):
    return {"name": nome, "output_type": "stream", "text": list(linhas)}


def _notebook_executado():
    return {
        "cells": [
            {"cell_type": "markdown", "id": "a", "metadata": {}, "source": ["# TJSC"]},
            {
                "cell_type": "code", "execution_count": 2, "id": "b",
                "metadata": {"execution": CARIMBOS, "tags": ["exemplo"]},
                "outputs": [
                    _stream("stderr", "\r", "Baixando CJSG TJSC:   0%|          | 0/2 [00:00<?, ?it/s]"),
                    _stream("stderr", "\r", "Baixando CJSG TJSC:  50%|█████     | 1/2 [00:00<00:00,  2.38it/s]"),
                    _stream("stderr", "\r", "Baixando CJSG TJSC: 100%|██████████| 2/2 [00:01<00:00,  1.18it/s]"),
                    _stream("stdout", "(20, 13)\n"),
                    _stream("stderr", "\n"),
                    TABELA,
                ],
                "source": ["df = tjsc.cjsg('dano moral', paginas=range(1, 3))\n", "df.shape"],
            },
        ],
        "metadata": METADATA_NOTEBOOK,
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def test_limpa_carimbos_e_barras_intermediarias():
    limpo = limpar_notebooks.limpar_notebook(_notebook_executado())
    celula = limpo["cells"][1]

    assert celula["metadata"] == {"tags": ["exemplo"]}
    assert celula["outputs"] == [
        _stream("stderr", "Baixando CJSG TJSC: 100%|██████████| 2/2 [00:01<00:00,  1.18it/s]"),
        _stream("stdout", "(20, 13)\n"),
        TABELA,
    ]
    assert limpo["metadata"] == METADATA_NOTEBOOK
    assert celula["execution_count"] == 2


def test_juntar_streams_mantem_quebras_de_linha_e_avisos():
    saidas = [
        _stream("stderr", "aviso: DeprecationWarning\n"),
        _stream("stderr", "\rBaixando: 0%"),
        _stream("stderr", "\rBaixando: 100%\n"),
        _stream("stderr", "\rProcessando: 50%\rProcessando: 100%\n"),
    ]

    assert limpar_notebooks.limpar_saidas(saidas) == [
        _stream("stderr", "aviso: DeprecationWarning\n", "Baixando: 100%\n", "Processando: 100%\n"),
    ]


def test_cr_no_fim_da_linha_nao_e_sobrescrita():
    saidas = [_stream("stdout", "linha windows\r\n")]

    assert limpar_notebooks.limpar_saidas(saidas) == saidas


def test_notebook_limpo_nao_e_reescrito(tmp_path):
    caminho = tmp_path / "limpo.ipynb"
    texto = limpar_notebooks.serializar(limpar_notebooks.limpar_notebook(_notebook_executado()))
    caminho.write_text(texto, encoding="utf-8")

    assert limpar_notebooks.main(["--check", str(caminho)]) == 0
    assert limpar_notebooks.main([str(caminho)]) == 0
    assert caminho.read_text(encoding="utf-8") == texto


def test_check_acusa_sem_gravar_e_modo_normal_grava(tmp_path, capsys):
    caminho = tmp_path / "executado.ipynb"
    original = json.dumps(_notebook_executado(), indent=1)
    caminho.write_text(original, encoding="utf-8")

    assert limpar_notebooks.main(["--check", str(caminho)]) == 1
    assert caminho.read_text(encoding="utf-8") == original
    assert "executado.ipynb: tem ruído de execução" in capsys.readouterr().err

    assert limpar_notebooks.main([str(caminho)]) == 0
    gravado = caminho.read_text(encoding="utf-8")
    assert "iopub" not in gravado
    assert gravado == limpar_notebooks.serializar(json.loads(gravado))
    assert limpar_notebooks.main(["--check", str(caminho)]) == 0
