"""Caracteriza a cobertura das partições antes de retomar um checkpoint."""

import pytest

from juscraper.courts.stf._checkpoint import Attempt, Checkpoint, Window


@pytest.fixture
def particao():
    return Window(
        lower="2026-01-01",
        upper="2026-01-04",
        total_before=4,
        children=[
            Window(lower="2026-01-01", upper="2026-01-02"),
            Window(lower="2026-01-03", upper="2026-01-04"),
        ],
    )


@pytest.fixture
def checkpoint():
    return Checkpoint(None, False, {})


@pytest.mark.parametrize("limites", [(None, None), ("2026-01-01", None), (None, "2026-01-04")])
def test_aceita_cobertura_contigua_com_limites_parciais(checkpoint, particao, limites):
    particao.lower, particao.upper = limites
    checkpoint._validate_partition(particao)


def test_aceita_tentativa_anterior_incompleta(checkpoint, particao):
    particao.attempts = [Attempt(started_at="2026-01-01", total_before=4)]
    checkpoint._validate_partition(particao)


@pytest.mark.parametrize("quantidade", [0, 1, 3])
def test_recusa_numero_de_filhos_diferente_de_dois(checkpoint, particao, quantidade):
    particao.children = [particao.children[0]] * quantidade
    with pytest.raises(ValueError, match=r"^Partição de checkpoint inválida\.$"):
        checkpoint._validate_partition(particao)


@pytest.mark.parametrize("concluida", [False, True])
def test_recusa_particao_sem_contagem_ou_com_tentativa_concluida(checkpoint, particao, concluida):
    if concluida:
        particao.attempts = [Attempt(started_at="2026-01-01", total_before=4, completed_at="2026-01-02")]
    else:
        particao.total_before = None
    with pytest.raises(ValueError, match=r"^Partição sem contagem ou com tentativa concluída\.$"):
        checkpoint._validate_partition(particao)


@pytest.mark.parametrize("indice,campo", [(0, "lower"), (0, "upper"), (1, "lower"), (1, "upper")])
def test_recusa_filho_datado_sem_limites(checkpoint, particao, indice, campo):
    setattr(particao.children[indice], campo, None)
    with pytest.raises(ValueError, match=r"^Partição sem limites\.$"):
        checkpoint._validate_partition(particao)


def test_recusa_residual_no_filho_esquerdo(checkpoint, particao):
    particao.children[0].missing = True
    with pytest.raises(ValueError, match=r"^Partição sem limites\.$"):
        checkpoint._validate_partition(particao)


@pytest.mark.parametrize("inicio_direita", ["2026-01-02", "2026-01-04"])
def test_recusa_sobreposicao_ou_lacuna(checkpoint, particao, inicio_direita):
    particao.children[1].lower = inicio_direita
    with pytest.raises(ValueError, match=r"^Partição com lacuna ou sobreposição\.$"):
        checkpoint._validate_partition(particao)


@pytest.mark.parametrize("campo,valor", [("lower", "2025-12-31"), ("upper", "2026-01-05")])
def test_recusa_limite_da_janela_nao_coberto(checkpoint, particao, campo, valor):
    setattr(particao, campo, valor)
    with pytest.raises(ValueError, match=r"^Partição não cobre os limites da janela\.$"):
        checkpoint._validate_partition(particao)


def test_residual_direito_dispensa_contiguidade_e_cobertura(checkpoint, particao):
    particao.children[1] = Window(missing=True)
    particao.lower = "2025-12-31"
    checkpoint._validate_partition(particao)


def test_residual_direito_ainda_exige_limites_esquerdos(checkpoint, particao):
    particao.children[1] = Window(missing=True)
    particao.children[0].lower = None
    with pytest.raises(ValueError, match=r"^Partição sem limites\.$"):
        checkpoint._validate_partition(particao)


def test_falha_de_contiguidade_precede_falha_de_cobertura(checkpoint, particao):
    particao.lower = "2025-12-31"
    particao.children[1].lower = "2026-01-04"
    with pytest.raises(ValueError, match=r"^Partição com lacuna ou sobreposição\.$"):
        checkpoint._validate_partition(particao)
