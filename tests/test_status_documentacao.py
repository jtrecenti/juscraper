"""Contratos offline do registro editorial e das duas tabelas geradas."""

import copy
import inspect
import runpy
import subprocess
import sys
import tomllib
from datetime import date
from importlib import import_module
from pathlib import Path

import pytest
from pydantic import ValidationError

from juscraper import _SCRAPERS

RAIZ = Path(__file__).resolve().parents[1]
GERADOR = RAIZ / "scripts/gerar_status.py"
MODULO = runpy.run_path(str(GERADOR))


@pytest.fixture
def dados():
    return {
        "validade_dias": 30,
        "fontes": [{
            "sigla": "tjap", "nome": "TJAP", "tipo": "tribunal", "endpoints": ["cjsg", "cjpg"],
            "observacoes": {"cjsg": {
                "estado": "indisponivel", "verificado_em": date(2026, 6, 7), "versao": "0.3.0",
                "motivo": "CAPTCHA | servidor\n<teste>",
                "cenario": "HTTP direto",
                "evidencias": ["https://github.com/jtrecenti/juscraper/issues/279"],
            }},
        }],
    }


def test_inventario_cobre_factory_e_metodos_reais():
    with (RAIZ / "status.toml").open("rb") as arquivo:
        registro = MODULO["Registro"].model_validate(tomllib.load(arquivo))
    assert {fonte.sigla for fonte in registro.fontes} == set(_SCRAPERS)
    for fonte in registro.fontes:
        modulo, nome = _SCRAPERS[fonte.sigla].split(":")
        classe = getattr(import_module(modulo), nome)
        for endpoint in fonte.endpoints:
            metodo = getattr(classe, endpoint)
            assert callable(metodo)
            assert "raise NotImplementedError" not in inspect.getsource(metodo)


@pytest.mark.parametrize("estado", ["funcionando", "degradado", "indisponivel"])
def test_validade_preserva_ultimo_estado_e_evidencia(dados, estado):
    dados["fontes"][0]["observacoes"]["cjsg"]["estado"] = estado
    registro = MODULO["Registro"].model_validate(dados)
    renderizar = MODULO["renderizar"]
    no_limite = renderizar(registro, date(2026, 7, 7))
    vencido = renderizar(registro, date(2026, 7, 8))
    rotulo = MODULO["ESTADOS"][estado]
    assert f"| `cjsg` | {rotulo} | 2026-06-07 | 2026-07-07 |" in no_limite
    assert f"Não verificado (último: {rotulo})" in vencido
    assert "| `cjpg` | Não verificado | - | - |" in vencido
    assert "CAPTCHA &#124; servidor &lt;teste&gt;" in vencido
    assert "https://github.com/jtrecenti/juscraper/issues/279" in vencido
    assert dados["fontes"][0]["observacoes"]["cjsg"]["estado"] == estado


def test_data_futura_nao_vira_funcionando(dados):
    registro = MODULO["Registro"].model_validate(dados)
    with pytest.raises(ValueError, match="futura"):
        MODULO["renderizar"](registro, date(2026, 6, 6))


@pytest.mark.parametrize("campo,valor", [
    ("estado", "ok"), ("estado", ""), ("versao", " "),
    ("evidencias", []), ("evidencias", ["javascript:alert(1)"]), ("verificado_em", "ontem"),
    ("motivo", ""), ("cenario", " "),
    ("campo_desconhecido", "erro"),
])
def test_rejeita_observacao_sem_contrato(dados, campo, valor):
    dados["fontes"][0]["observacoes"]["cjsg"][campo] = valor
    with pytest.raises(ValidationError):
        MODULO["Registro"].model_validate(dados)


def test_tentativa_inconclusiva_preserva_motivo_sem_prazo_de_validade(dados):
    dados["fontes"][0]["observacoes"]["cjsg"]["estado"] = "nao_verificado"
    registro = MODULO["Registro"].model_validate(dados)
    for hoje in (date(2026, 6, 7), date(2026, 8, 1)):
        texto = MODULO["renderizar"](registro, hoje)
        assert "| `cjsg` | Não verificado | 2026-06-07 | - |" in texto
        assert "CAPTCHA &#124; servidor &lt;teste&gt;" in texto
        assert "último: Não verificado" not in texto


@pytest.mark.parametrize("erro", ["sigla", "endpoint", "observacao", "prazo"])
def test_rejeita_inventario_inconsistente(dados, erro):
    fonte = dados["fontes"][0]
    if erro == "sigla":
        dados["fontes"].append(copy.deepcopy(fonte))
    elif erro == "endpoint":
        fonte["endpoints"].append("cjsg")
    elif erro == "observacao":
        fonte["endpoints"] = ["cjpg"]
    else:
        dados["validade_dias"] = 0
    with pytest.raises(ValidationError):
        MODULO["Registro"].model_validate(dados)


@pytest.mark.parametrize("texto", ["sem marcadores", "<!-- status:fim --><!-- status:inicio -->",
                                   "<!-- status:inicio --><!-- status:inicio --><!-- status:fim -->"])
def test_rejeita_marcadores_ambiguos(texto):
    with pytest.raises(ValueError):
        MODULO["substituir_bloco"](texto, "novo")


def executar_cli(raiz, *opcoes):
    return subprocess.run(
        [sys.executable, str(GERADOR), "--raiz", str(raiz), *opcoes],
        capture_output=True, text=True, check=False,
    )


def test_cli_detecta_drift_sem_escrever_e_regenera_preservando_prosa(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "status.toml").write_bytes((RAIZ / "status.toml").read_bytes())
    antigo = "Introdução autoral\n<!-- status:inicio -->\nobsoleto\n<!-- status:fim -->\nAutenticação\n"
    caminhos = [tmp_path / "README.md", tmp_path / "docs/index.qmd"]
    for caminho in caminhos:
        caminho.write_text(antigo, encoding="utf-8")
    assert executar_cli(tmp_path, "--check").returncode == 1
    assert all(caminho.read_text(encoding="utf-8") == antigo for caminho in caminhos)
    assert executar_cli(tmp_path).returncode == 0
    assert executar_cli(tmp_path, "--check").returncode == 0
    for caminho in caminhos:
        texto = caminho.read_text(encoding="utf-8")
        assert texto.startswith("Introdução autoral\n")
        assert texto.endswith("\nAutenticação\n")
    assert caminhos[0].read_bytes() == caminhos[1].read_bytes()
    assert "Implementações e status" in caminhos[1].read_text(encoding="utf-8")
    caminhos[1].write_text("sem marcadores", encoding="utf-8")
    caminhos[0].write_text(antigo, encoding="utf-8")
    assert executar_cli(tmp_path).returncode == 1
    assert caminhos[0].read_text(encoding="utf-8") == antigo


def test_tabelas_versionadas_estao_sincronizadas():
    resultado = executar_cli(RAIZ, "--check")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_xfail_tjap_so_absorve_bloqueio_conhecido(pytester):
    pytester.makepyfile('''
        import pytest
        from tests.tjap.test_tjap_cjsg import TestCJSGTJAP as ClasseOriginal
        from juscraper.courts.tjap.exceptions import TJAPSecurityCheckError

        marcador = next(m for m in ClasseOriginal.pytestmark if m.name == "xfail")
        pytestmark = pytest.mark.xfail(*marcador.args, **marcador.kwargs)

        def test_bloqueio():
            raise TJAPSecurityCheckError("A verificação de segurança falhou", "")

        def test_regressao():
            raise ValueError("parser quebrado")

        def test_recuperacao():
            assert True
    ''')
    resultado = pytester.runpytest("-p", "no:asyncio")
    resultado.assert_outcomes(xfailed=1, failed=1, xpassed=1)
