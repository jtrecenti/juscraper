"""Caracteriza as invariantes de retomada antes de qualquer coleta."""

import pytest

from juscraper.courts.stf._checkpoint import Attempt, Checkpoint, Window


@pytest.fixture
def checkpoint(tmp_path):
    aberto = Checkpoint(
        tmp_path / "checkpoint", resume=False, identity={"base": "acordaos", "pages": None, "page_size": 1},
    )
    yield aberto
    aberto.close()


def validar_na_retomada(checkpoint, janela):
    # A validação só roda quando a coleta retoma um diretório; o erro chega embrulhado, e o `match` busca dentro dele.
    checkpoint.manifest.root = janela
    checkpoint.save()
    checkpoint.close()
    retomado = Checkpoint(checkpoint.directory, resume=True, identity=checkpoint.manifest.identity)
    retomado.close()


def tentativa(checkpoint, identificadores=("a", "b"), *, concluida=True):
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
        ({"completed_at": "fim"}, "Janela concluída com contagens diferentes"),
        ({"completed_at": "fim", "total_before": 1, "total_after": 2}, "Janela concluída com contagens diferentes"),
        ({"completed_at": "fim", "total_before": 0, "total_after": 0}, "sem tentativa"),
    ],
)
def test_rejeita_janela_invalida(checkpoint, campos, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        validar_na_retomada(checkpoint, Window(**campos))


@pytest.mark.parametrize("concluida", [False, True])
@pytest.mark.parametrize("duplicacao", ["identidade", "numero"])
def test_rejeita_duplicatas_inclusive_em_tentativa_incompleta(checkpoint, concluida, duplicacao):
    coleta = tentativa(checkpoint, concluida=concluida)
    if duplicacao == "identidade":
        coleta.pages[1] = checkpoint.page([{"base": "acordaos", "id": "a"}], 2)
    else:
        coleta.pages[1].number = 1
    with pytest.raises(ValueError, match="Páginas duplicadas"):
        validar_na_retomada(checkpoint, Window(attempts=[coleta]))


def test_identidades_podem_reaparecer_em_tentativas_distintas(checkpoint):
    validar_na_retomada(checkpoint, Window(attempts=[tentativa(checkpoint, concluida=False), tentativa(checkpoint)]))


def test_valida_tentativa_em_qualquer_posicao(checkpoint):
    do_meio = tentativa(checkpoint, concluida=False)
    do_meio.pages[1].number = 1
    janela = Window(attempts=[tentativa(checkpoint, concluida=False), do_meio, tentativa(checkpoint)])
    with pytest.raises(ValueError, match="Páginas duplicadas"):
        validar_na_retomada(checkpoint, janela)


@pytest.mark.parametrize("concluida", [False, True])
def test_janela_exige_ultima_tentativa_concluida_e_contagem_igual(checkpoint, concluida):
    # Só a primeira tentativa tem o total da janela: a comparação precisa olhar a última.
    janela = Window(
        completed_at="fim", total_before=3, total_after=3,
        attempts=[tentativa(checkpoint, ("a", "b", "c")), tentativa(checkpoint, concluida=concluida)],
    )
    mensagem = "Janela e tentativa" if concluida else "sem tentativa concluída"
    with pytest.raises(ValueError, match=mensagem):
        validar_na_retomada(checkpoint, janela)


@pytest.mark.parametrize(
    ("problema", "mensagem"),
    [
        ("numero", "contagens ou páginas inconsistentes"),
        ("contagem", "Página de checkpoint incompleta"),
    ],
    ids=["numero", "contagem"],
)
def test_tentativa_concluida_confere_numero_e_contagem_de_cada_pagina(checkpoint, problema, mensagem):
    coleta = tentativa(checkpoint, ("a",))
    if problema == "numero":
        coleta.pages[0].number = 2
    else:
        coleta.pages[0] = checkpoint.page([], 1)
    with pytest.raises(ValueError, match=mensagem):
        validar_na_retomada(checkpoint, Window(attempts=[coleta]))


@pytest.mark.parametrize("paginas", [None, [1]])
def test_contagem_de_identidades_completa_so_para_todas_as_paginas(checkpoint, paginas, monkeypatch):
    checkpoint.manifest.identity["pages"] = paginas
    coleta = tentativa(checkpoint, ("a",))
    coleta.total_before = coleta.total_after = 2
    if paginas is None:
        # Acima do teto da fonte a segunda página é vazia e coerente com o descritor, mas falta um documento.
        monkeypatch.setattr("juscraper.courts.stf.download.MAX_REGISTROS", 1)
        coleta.pages.append(checkpoint.page([], 2))
        with pytest.raises(ValueError, match="páginas faltantes"):
            validar_na_retomada(checkpoint, Window(attempts=[coleta]))
    else:
        validar_na_retomada(checkpoint, Window(attempts=[coleta]))


@pytest.mark.parametrize("problema", [None, "incompleto", "contagem", "descendente", "lacuna"])
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
        "lacuna": "lacuna ou sobreposição",
    }
    if problema == "incompleto":
        direita.completed_at = None
    elif problema == "contagem":
        janela.total_before = janela.total_after = 3
    elif problema == "descendente":
        direita.upper = "2020-01-01"
    elif problema == "lacuna":
        direita.lower = direita.upper = "2020-01-03"
    if problema:
        with pytest.raises(ValueError, match=mensagens[problema]):
            validar_na_retomada(checkpoint, janela)
    else:
        validar_na_retomada(checkpoint, janela)


@pytest.mark.parametrize(
    "par", ["tentativas_antes_das_filhas", "filhas_antes_da_conclusao", "tentativa_antes_das_faltantes"],
)
def test_violacoes_simultaneas_seguem_a_ordem_das_conferencias(checkpoint, par):
    # Cada janela viola mais de uma invariante, e vale a mensagem da conferência que roda primeiro.
    esquerda = Window(
        lower="2020-01-01", upper="2020-01-01", completed_at="fim",
        total_before=1, total_after=1, attempts=[tentativa(checkpoint, ("a",))],
    )
    invertida = Window(
        lower="2020-01-02", upper="2020-01-01", completed_at="fim",
        total_before=1, total_after=1, attempts=[tentativa(checkpoint, ("b",))],
    )
    mensagens = {
        "tentativas_antes_das_filhas": "Páginas duplicadas", "filhas_antes_da_conclusao": "invertido",
        "tentativa_antes_das_faltantes": "contagens ou páginas inconsistentes",
    }
    if par == "tentativas_antes_das_filhas":
        duplicada = tentativa(checkpoint, concluida=False)
        duplicada.pages[1].number = 1
        janela = Window(total_before=2, children=[esquerda, invertida], attempts=[duplicada])
    elif par == "filhas_antes_da_conclusao":
        janela = Window(total_before=3, total_after=3, completed_at="fim", children=[esquerda, invertida])
    else:
        incoerente = tentativa(checkpoint, ("a",))
        incoerente.total_before = 2
        janela = Window(attempts=[incoerente])
    with pytest.raises(ValueError, match=mensagens[par]):
        validar_na_retomada(checkpoint, janela)
