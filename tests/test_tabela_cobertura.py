"""Trava a tabela de cobertura do README e da documentação contra o código.

A tabela é gerada por ``scripts/tabela_cobertura.py``. Quando um tribunal ou
endpoint entra, sai ou vira stub, ``test_documentacao_em_dia`` reprova até o
script ser rodado de novo.
"""

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("tabela_cobertura", RAIZ / "scripts" / "tabela_cobertura.py")
assert _spec is not None
assert _spec.loader is not None
tabela_cobertura = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tabela_cobertura)


def test_documentacao_em_dia():
    assert tabela_cobertura.main(["--check"]) == 0, "rode `uv run python scripts/tabela_cobertura.py`"


class _Exemplos:
    def stub_com_docstring(self):
        """Não implementado."""
        raise NotImplementedError("sem consulta")

    def stub_sem_chamada(self):
        raise NotImplementedError

    def valida_e_consulta(self, valor):
        if valor is None:
            raise NotImplementedError("ramo de validação")
        return valor

    def levanta_outra_excecao(self):
        raise ValueError("não é stub")


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("stub_com_docstring", True),
        ("stub_sem_chamada", True),
        ("valida_e_consulta", False),
        ("levanta_outra_excecao", False),
    ],
)
def test_e_stub(nome, esperado):
    assert tabela_cobertura.e_stub(getattr(_Exemplos, nome)) is esperado


def test_heranca_e_stubs_na_cobertura():
    grupos = tabela_cobertura.cobertura()
    # TJAC herda o cjsg da base eSAJ e não tem consulta processual.
    assert grupos["tribunais"]["tjac"] == ["cjsg"]
    # TJMG implementa cposg; o cpopg dele é stub.
    assert grupos["tribunais"]["tjmg"] == ["cposg", "cjsg"]
    # TRF1 recebe o cpopg da base ``_trf``.
    assert grupos["tribunais"]["trf1"] == ["cpopg"]
    assert set(grupos["tribunais"]) | set(grupos["agregadores"]) == set(tabela_cobertura.REGISTRO)


def test_check_reprova_tabela_desatualizada(tmp_path, monkeypatch):
    arquivo = tmp_path / "README.md"
    arquivo.write_text(
        f"antes\n{tabela_cobertura.INICIO}\n| velho |\n{tabela_cobertura.FIM}\ndepois\n", encoding="utf-8"
    )
    titulos_readme = tabela_cobertura.ARQUIVOS[tabela_cobertura.RAIZ / "README.md"]
    monkeypatch.setattr(tabela_cobertura, "RAIZ", tmp_path)
    monkeypatch.setattr(tabela_cobertura, "ARQUIVOS", {arquivo: titulos_readme})

    assert tabela_cobertura.main(["--check"]) == 1
    assert "| velho |" in arquivo.read_text(encoding="utf-8")

    assert tabela_cobertura.main([]) == 0
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.startswith("antes\n")
    assert texto.endswith("\ndepois\n")
    assert "| TJMG     | cposg, cjsg |" in texto
    assert tabela_cobertura.main(["--check"]) == 0


def test_marcadores_ausentes(tmp_path):
    with pytest.raises(SystemExit, match="marcadores"):
        tabela_cobertura.substituir("sem marcadores", "bloco", tmp_path / "x.md")


def test_json(capsys):
    assert tabela_cobertura.main(["--json"]) == 0
    saida = json.loads(capsys.readouterr().out)
    assert saida == tabela_cobertura.cobertura()
    assert saida["tribunais"]["trf3"] == ["cpopg", "cjsg"]
