"""``avisar`` atribui o aviso ao primeiro quadro fora do pacote ``juscraper``."""
from __future__ import annotations

import ast
import pathlib
import warnings

import pytest

import juscraper
from juscraper.core.avisos import avisar
from juscraper.core.failures import avisar_falhas


def test_aviso_chamado_daqui_aponta_para_esta_linha():
    with pytest.warns(UserWarning, match="direto") as registro:
        avisar("direto")  # linha do aviso

    assert registro[0].filename == __file__
    assert "linha do aviso" in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()[registro[0].lineno - 1]


def test_aviso_emitido_dentro_do_pacote_pula_os_quadros_do_pacote():
    # ``avisar_falhas`` chama ``avisar`` de dentro do pacote: o aviso tem de
    # sair nesta linha, e não em ``core/failures.py``.
    with pytest.warns(UserWarning, match="Teste.metodo") as registro:
        avisar_falhas(["a"], "Teste.metodo", "consulta(s)")  # linha do aviso

    assert registro[0].filename == __file__
    assert "linha do aviso" in pathlib.Path(__file__).read_text(encoding="utf-8").splitlines()[registro[0].lineno - 1]


def test_categoria_e_repassada():
    with pytest.warns(DeprecationWarning, match="velho"):
        avisar("velho", DeprecationWarning)


def test_nenhum_warnings_warn_fora_de_avisos():
    # Gate: aviso emitido direto com ``warnings.warn`` volta a depender de
    # ``stacklevel`` contado à mão, que um decorador ou helper desloca.
    raiz = pathlib.Path(juscraper.__file__).parent
    permitido = raiz / "core" / "avisos.py"
    diretos = [
        f"{arquivo.relative_to(raiz)}:{no.lineno}"
        for arquivo in sorted(raiz.rglob("*.py"))
        if arquivo != permitido
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
        if isinstance(no, ast.Call) and ast.unparse(no.func) in {"warnings.warn", "warn"}
    ]

    assert diretos == []


def test_filtro_de_aviso_continua_valendo():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(UserWarning, match="vira erro"):
            avisar("vira erro")
