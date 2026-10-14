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


def _emite_aviso_direto(no: ast.AST) -> bool:
    if isinstance(no, ast.Call):
        return ast.unparse(no.func) in {"warnings.warn", "warnings.warn_explicit"}
    if isinstance(no, ast.ImportFrom) and no.module == "warnings":
        return any(nome.name in {"warn", "warn_explicit", "*"} for nome in no.names)
    if isinstance(no, ast.Import):
        # ``import warnings as w`` esconderia ``w.warn`` da checagem acima.
        return any(nome.name == "warnings" and nome.asname for nome in no.names)
    return False


def test_nenhum_warnings_warn_fora_de_avisos():
    # Gate: aviso emitido direto com ``warnings.warn`` volta a depender de
    # ``stacklevel`` contado à mão, que um decorador ou helper desloca.
    # ``warnings.filterwarnings`` e ``catch_warnings`` continuam permitidos.
    raiz = pathlib.Path(juscraper.__file__).parent
    permitido = raiz / "core" / "avisos.py"
    diretos = [
        f"{arquivo.relative_to(raiz)}:{no.lineno}"
        for arquivo in sorted(raiz.rglob("*.py"))
        if arquivo != permitido
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8")))
        if _emite_aviso_direto(no)
    ]

    assert diretos == []


@pytest.mark.parametrize(
    "trecho",
    [
        "import warnings\nwarnings.warn('x', stacklevel=2)",
        "import warnings\nwarnings.warn_explicit('x', UserWarning, 'f', 1)",
        "from warnings import warn\nwarn('x', stacklevel=2)",
        "import warnings as w\nw.warn('x', stacklevel=2)",
    ],
)
def test_gate_reconhece_as_formas_de_emitir_aviso(trecho):
    assert any(_emite_aviso_direto(no) for no in ast.walk(ast.parse(trecho)))


def test_gate_permite_filtrar_avisos():
    trecho = "import warnings\nwarnings.filterwarnings('ignore')\nwith warnings.catch_warnings():\n    pass"
    assert not any(_emite_aviso_direto(no) for no in ast.walk(ast.parse(trecho)))


def test_filtro_de_aviso_continua_valendo():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(UserWarning, match="vira erro"):
            avisar("vira erro")
