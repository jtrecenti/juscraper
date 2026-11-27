"""Testes unitarios da parseria de paginacao TJPE (refs #87)."""
from __future__ import annotations

import re

import pytest

from juscraper.courts.tjpe.download import extract_total_docs, is_escolha_page, is_results_page, is_sem_resultados_page
from tests._helpers import load_sample


def _sample(name: str) -> str:
    return load_sample("tjpe", f"cjsg/{name}")


_LINHA_DA_CONTAGEM = re.compile(r"<tr>\s*<th>\s*<label>Documentos encontrados: </label>.*?</tr>", re.DOTALL)
_PRIMEIRA_EMENTA = "DIREITO CIVIL. A&Ccedil;&Atilde;O DE COBRAN&Ccedil;A"


def _com_aviso_na_ementa(html: str) -> str:
    """A primeira ementa de ``simples_resultado.html`` passa a dizer "nenhum documento encontrado nos autos"."""
    assert _PRIMEIRA_EMENTA in html
    return html.replace(_PRIMEIRA_EMENTA, "nenhum documento encontrado nos autos", 1)


def resultado_sem_cabecalho_com_aviso_na_ementa() -> str:
    """HTML derivado de ``simples_resultado.html``, sem a linha da contagem e com o aviso numa ementa."""
    sem_contagem, n = _LINHA_DA_CONTAGEM.subn("", _sample("simples_resultado.html"))
    assert n == 1
    assert "documentos encontrados" not in sem_contagem.lower()
    return _com_aviso_na_ementa(sem_contagem)


def test_extract_total_docs_resultado_normal():
    assert extract_total_docs(_sample("step_03_resultado.html")) == 953


def test_extract_total_docs_simples_resultado():
    assert extract_total_docs(_sample("simples_resultado.html")) == 988


def test_extract_total_docs_escolha_page_fallback():
    assert extract_total_docs(_sample("step_02_escolha.html")) == 953


def test_extract_total_docs_ementa_com_o_marcador_de_zero_nao_zera():
    """HTML derivado do sample real ``simples_resultado.html``.

    A primeira ementa passa a dizer "nenhum documento encontrado nos autos";
    o cabeçalho "Documentos encontrados: 988" continua valendo.
    """
    assert extract_total_docs(_com_aviso_na_ementa(_sample("simples_resultado.html"))) == 988


def test_extract_total_docs_resultado_sem_contagem_com_aviso_na_ementa_nao_zera():
    """Sem o cabeçalho, a frase da ementa não conta como busca vazia: sem total."""
    assert extract_total_docs(resultado_sem_cabecalho_com_aviso_na_ementa()) is None


def test_extract_total_docs_sem_o_cabecalho_ementa_com_n_documentos_encontrados_nao_vira_total():
    """HTML derivado do sample real ``simples_resultado.html``, com o cabeçalho fora do seletor.

    A primeira ementa passa a dizer "3 documentos encontrados". No HTML da
    página, o rótulo "Documentos encontrados:" vem separado do número por tags,
    e a ementa não pode virar o total da busca: sem total, o download levanta.
    """
    original = _sample("simples_resultado.html")
    assert original.count("table-header-resultado") == 1
    html = original.replace("table-header-resultado", "table-header-novo")
    html = html.replace(_PRIMEIRA_EMENTA, "apreensão de 3 documentos encontrados", 1)
    assert extract_total_docs(html) is None


def test_extract_total_docs_no_results_returns_zero():
    assert extract_total_docs(_sample("no_results.html")) == 0


def test_extract_total_docs_resilient_to_table_class_change():
    html = (
        '<div class="painel-novo">'
        "<span>Documentos encontrados: 1234</span></div>"
    )
    assert extract_total_docs(html) == 1234


def test_extract_total_docs_sem_contagem_nem_aviso_da_none():
    html = "<div>HTML totalmente diferente sem informacao de contagem</div>"
    assert extract_total_docs(html) is None


def test_is_results_page_case_insensitive():
    html = "<html><body>DOCUMENTOS ENCONTRADOS: 5<br>DOCUMENTO 1</body></html>"
    assert is_results_page(html) is True


def test_is_escolha_page_case_insensitive():
    html = "<html><body>5 DOCUMENTOS ENCONTRADOS</body></html>"
    assert is_escolha_page(html) is True
    assert is_results_page(html) is False


@pytest.mark.parametrize(
    ("sample", "esperado"),
    [
        ("no_results.html", True),
        ("no_results_todos.html", True),
        ("step_02_escolha.html", False),
        ("step_03_resultado.html", False),
    ],
)
def test_is_sem_resultados_page(sample, esperado):
    assert is_sem_resultados_page(load_sample("tjpe", f"cjsg/{sample}")) is esperado


def test_is_sem_resultados_page_ignora_o_aviso_fora_da_tabela_de_escolha():
    """A frase numa ementa, fora de ``div.escolha-resultado-table``, não é busca vazia."""
    assert is_sem_resultados_page(resultado_sem_cabecalho_com_aviso_na_ementa()) is False
