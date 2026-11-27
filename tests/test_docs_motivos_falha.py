"""Trava a tabela "Per-row failures" de ``docs/api-conventions.qmd`` contra os motivos de falha do código.

A tabela lista exatamente os valores de :data:`juscraper.core.failures.MOTIVOS_FALHA`.
Os motivos montados na hora (``http_404``, ``retry_esgotado_429``) e os das
outras famílias (as exceções com ``motivo`` dos downloads em lote do eSAJ e a
coluna ``error`` de ``contar_processos`` do DataJud, quando o erro tem motivo
no vocabulário) passam pela mesma verificação, :func:`documentado`, em que
``<status>`` vale um código HTTP. O ``"<Classe>: <mensagem>"`` do DataJud fora
do vocabulário fica nos testes de ``tests/datajud``.
"""

from __future__ import annotations

import re
from functools import cache
from pathlib import Path

import pytest
import requests

import juscraper as jus
from juscraper.aggregators.datajud import client as datajud_client
from juscraper.core.exceptions import RetryExhaustedError
from juscraper.core.failures import COLUNA_MOTIVO_FALHA, MOTIVOS_FALHA, motivo_falha
from juscraper.courts._esaj.acordao import _LOTE_ACORDAO
from juscraper.courts._esaj.acordao_cjsg import _LOTE_ACORDAO_CJSG
from juscraper.courts._esaj.sentenca import _LOTE_SENTENCA

DOC = Path(__file__).resolve().parents[1] / "docs" / "api-conventions.qmd"
SECAO = "\n## Per-row failures\n"


@cache
def motivos_da_tabela() -> frozenset[str]:
    """Primeira coluna da tabela da seção, sem o cabeçalho e o separador."""
    texto = DOC.read_text(encoding="utf-8")
    assert SECAO in texto, f"{DOC.name} sem a seção 'Per-row failures'"
    secao = texto.split(SECAO, 1)[1].split("\n## ", 1)[0]
    celulas = [linha.split("|")[1].strip().strip("`") for linha in secao.splitlines() if linha.startswith("|")]
    assert celulas[:2] == [COLUNA_MOTIVO_FALHA, "---"], "a tabela começa pelo cabeçalho `motivo_falha`"
    return frozenset(celulas[2:])


def documentado(motivo: str) -> bool:
    """Diz se o motivo concreto tem linha na tabela; ``<status>`` casa um código HTTP de três dígitos."""
    status = re.escape("<status>")
    return any(
        re.fullmatch(re.escape(linha).replace(status, r"[1-5]\d{2}"), motivo) for linha in motivos_da_tabela()
    )


def _http_error(status: int) -> requests.HTTPError:
    resposta = requests.Response()
    resposta.status_code = status
    return requests.HTTPError(f"{status}", response=resposta)


def test_tabela_lista_exatamente_o_vocabulario():
    assert motivos_da_tabela() == set(MOTIVOS_FALHA), f"{DOC.name} > Per-row failures fora de MOTIVOS_FALHA"


@pytest.mark.parametrize(
    ("motivo", "esperado"),
    [
        ("http_404", True),
        ("retry_esgotado_503", True),
        ("timeout", True),
        ("http_", False),
        ("http_abc", False),
        ("http_<status>_x", False),
        ("retry_esgotado", False),
        ("motivo_inventado", False),
    ],
)
def test_documentado_so_aceita_o_status_no_lugar_de_status(motivo, esperado):
    assert documentado(motivo) is esperado


@pytest.mark.parametrize(
    "exc", [_http_error(404), _http_error(500), RetryExhaustedError(429, 3), RetryExhaustedError(503, 3)]
)
def test_motivo_com_status_montado_da_excecao_esta_documentado(exc):
    assert documentado(motivo_falha(exc))


def _subclasses(classe: type[object]) -> list[type]:
    return [classe, *(sub for direta in classe.__subclasses__() for sub in _subclasses(direta))]


def test_motivos_das_excecoes_dos_lotes_do_esaj_estao_documentados():
    erros = {erro for lote in (_LOTE_ACORDAO, _LOTE_ACORDAO_CJSG, _LOTE_SENTENCA) for erro in lote.erros_com_motivo}
    motivos = {
        classe.__name__: classe.motivo for erro in erros for classe in _subclasses(erro) if hasattr(classe, "motivo")
    }
    assert motivos, "nenhuma exceção com motivo nos lotes"
    assert {nome: m for nome, m in motivos.items() if not documentado(m)} == {}


def _contagem_que_levanta(erro):
    def fake_call(**_kwargs):
        raise erro

    return fake_call


@pytest.mark.parametrize(
    "fake_call",
    [
        pytest.param(_contagem_que_levanta(_http_error(503)), id="http"),
        pytest.param(lambda **_kwargs: {"hits": {"total": []}}, id="contagem-fora-do-formato"),
    ],
)
def test_coluna_error_do_datajud_esta_documentada(monkeypatch, fake_call):
    monkeypatch.setattr(datajud_client, "call_datajud_api", fake_call)

    motivo = jus.scraper("datajud").contar_processos(tribunal="TJSP").iloc[0]["error"]

    assert documentado(motivo), motivo
