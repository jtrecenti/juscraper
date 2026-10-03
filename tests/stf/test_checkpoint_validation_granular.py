"""Caracteriza as invariantes de retomada antes de qualquer coleta."""

import pytest

from juscraper.courts.stf._checkpoint import Attempt, Checkpoint, Window


@pytest.fixture
def checkpoint():
    return Checkpoint(None, False, {"base": "acordaos", "pages": None, "page_size": 1})


def tentativa(checkpoint, identificadores=("a", "b"), concluida=True):
    return Attempt(
        started_at="início",
        total_before=len(identificadores),
        total_after=len(identificadores) if concluida else None,
        completed_at="fim" if concluida else None,
        pages=[
            checkpoint.page([{"base": "acordaos", "id": identificador}], numero)
            for numero, identificador in enumerate(identificadores, 1)
        ],
    )


@pytest.mark.parametrize(
    ("campos", "mensagem"),
    [
        ({"lower": "inválida"}, "Invalid isoformat"),
        ({"upper": "inválida"}, "Invalid isoformat"),
        ({"lower": "2020-02-01", "upper": "2020-01-01"}, "invertido"),
        ({"missing": True, "lower": "2020-01-01"}, "Residual"),
        ({"missing": True, "upper": "2020-01-01"}, "Residual"),
        ({"missing": True, "children": [Window()]}, "Residual"),
        ({"completed_at": "fim"}, "contagens diferentes"),
        ({"completed_at": "fim", "total_before": 1, "total_after": 2}, "contagens diferentes"),
        ({"completed_at": "fim", "total_before": 0, "total_after": 0}, "sem tentativa"),
    ],
)
def test_rejeita_janela_invalida(checkpoint, campos, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        checkpoint._validate(Window(**campos))


@pytest.mark.parametrize("concluida", [False, True])
@pytest.mark.parametrize("duplicacao", ["identidade", "numero"])
def test_rejeita_duplicatas_inclusive_em_tentativa_incompleta(checkpoint, concluida, duplicacao):
    coleta = tentativa(checkpoint, concluida=concluida)
    if duplicacao == "identidade":
        coleta.pages[1] = checkpoint.page([{"base": "acordaos", "id": "a"}], 2)
    else:
        coleta.pages[1].number = 1
    with pytest.raises(ValueError, match="Páginas duplicadas"):
        checkpoint._validate(Window(attempts=[coleta]))


def test_identidades_podem_reaparecer_em_tentativas_distintas(checkpoint):
    checkpoint._validate(Window(attempts=[tentativa(checkpoint, concluida=False), tentativa(checkpoint)]))


@pytest.mark.parametrize("concluida", [False, True])
def test_janela_exige_ultima_tentativa_concluida_e_contagem_igual(checkpoint, concluida):
    janela = Window(
        completed_at="fim", total_before=3, total_after=3,
        attempts=[tentativa(checkpoint), tentativa(checkpoint, concluida=concluida)],
    )
    mensagem = "Janela e tentativa" if concluida else "sem tentativa concluída"
    with pytest.raises(ValueError, match=mensagem):
        checkpoint._validate(janela)


@pytest.mark.parametrize("paginas", [None, [1]])
def test_contagem_de_identidades_completa_so_para_todas_as_paginas(checkpoint, paginas):
    checkpoint.manifest.identity["pages"] = paginas
    coleta = tentativa(checkpoint, ("a",))
    coleta.total_before = coleta.total_after = 2
    if paginas is None:
        # O descritor promete duas páginas válidas, mas a memória contém só um documento.
        coleta.pages.append(checkpoint.page([], 2))
        coleta.pages[-1].count = 1
        with pytest.raises(ValueError, match="páginas faltantes"):
            checkpoint._validate(Window(attempts=[coleta]))
    else:
        checkpoint._validate(Window(attempts=[coleta]))


@pytest.mark.parametrize("problema", [None, "incompleto", "contagem", "descendente"])
def test_valida_particao_concluida_e_descendentes(checkpoint, problema):
    esquerda = Window(
        lower="2020-01-01", upper="2020-01-01", completed_at="fim",
        total_before=1, total_after=1, attempts=[tentativa(checkpoint, ("a",))],
    )
    direita = Window(
        lower="2020-01-02", upper="2020-01-02", completed_at="fim",
        total_before=1, total_after=1, attempts=[tentativa(checkpoint, ("b",))],
    )
    janela = Window(total_before=2, total_after=2, completed_at="fim", children=[esquerda, direita])
    mensagens = {
        "incompleto": "filhos incompletos", "contagem": "Partição com contagens", "descendente": "invertido",
    }
    if problema == "incompleto":
        direita.completed_at = None
    elif problema == "contagem":
        janela.total_before = janela.total_after = 3
    elif problema == "descendente":
        direita.upper = "2020-01-01"
    if problema:
        with pytest.raises(ValueError, match=mensagens[problema]):
            checkpoint._validate(janela)
    else:
        checkpoint._validate(janela)
