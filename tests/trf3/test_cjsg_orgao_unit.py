"""Unit tests for reading the órgão dropdown of the TRF3 ``cjsg`` form.

Each tab of the portal (``home/index/{n}``) carries its own ``select#orgao``;
every option has a label (the text shown) and an indexed name
(``data-val-jef``). The samples are the real tabs captured by
``tests/fixtures/capture/trf3_cjsg.py``.
"""
from __future__ import annotations

from collections import Counter

from juscraper.courts.trf3.cjsg_download import _opcoes_orgao
from tests._helpers import load_sample


def _opcoes(nome: str) -> list[tuple[str, str]]:
    return _opcoes_orgao(load_sample("trf3", f"cjsg/{nome}"))


def test_opcoes_orgao_aba_de_acordaos():
    """36 options, 35 labels: ``5ª Turma`` names two indexed órgãos."""
    opcoes = _opcoes("index_acordaos.html")

    assert len(opcoes) == 36
    rotulos = Counter(rotulo for rotulo, _ in opcoes)
    assert len(rotulos) == 35
    assert [r for r, n in rotulos.items() if n > 1] == ["5ª Turma"]
    assert {nome for rotulo, nome in opcoes if rotulo == "5ª Turma"} == {"QUINTA TURMA - 1a. SEÇÃO", "QUINTA TURMA"}
    assert ("3ª Turma", "TERCEIRA TURMA") in opcoes
    assert all(rotulo != "Selecione..." for rotulo, _ in opcoes)


def test_opcoes_orgao_aba_de_turmas_recursais():
    """18 options, no repeated label, every one with an indexed name."""
    opcoes = _opcoes("index_turmas_recursais.html")

    assert len(opcoes) == 18
    assert len({rotulo for rotulo, _ in opcoes}) == 18
    assert ("11ª Turma Recursal da Seção Judiciária de São Paulo", "11ª TURMA RECURSAL DE SÃO PAULO") in opcoes


def test_opcoes_orgao_sem_dropdown_devolve_vazio():
    """A page without ``select#orgao`` (a result list) yields no options."""
    assert _opcoes("no_results.html") == []
