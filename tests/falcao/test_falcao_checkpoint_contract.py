"""Contratos (offline) da retomada de coleta do Falcao (``checkpoint_dir`` e ``resume``).

O backend bloqueia o IP por cota diária: a retomada não pode gastar requisição
nas páginas já gravadas, nem misturar buscas diferentes no mesmo diretório.
"""
import json
from pathlib import Path

import pytest
import requests
import responses

import juscraper as jus
from juscraper.aggregators.falcao.download import SEARCH_URL
from tests.falcao.test_falcao_contract import AVISO_DE_ORDEM, _paginas_pedidas, _register, _sample

_POR_PAGINA = len(_sample("acordaos")["documentos"])


@pytest.fixture
def falcao():
    return jus.scraper("falcao", verbose=0, sleep_time=0)


def _bloquear_por_cota() -> None:
    responses.add(responses.GET, SEARCH_URL, status=429,
                  headers={"x-rate-limit-retry-after-seconds": "20880"})


def _interromper_na_pagina_3(falcao, checkpoint: Path, total: int = 40) -> None:
    """Primeira sessão: recebe as páginas 1 e 2 e a cota acaba na 3."""
    for pagina in (1, 2):
        _register("acordaos", total=total, pagina=pagina)
    _bloquear_por_cota()
    with pytest.raises(requests.HTTPError) as captura:
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)
    assert any(str(checkpoint) in nota and "resume=True" in nota for nota in captura.value.__notes__)
    responses.reset()


def _paginas_em_disco(checkpoint: Path) -> list[str]:
    return sorted(p.name for p in checkpoint.glob("acordaos_*.json"))


@responses.activate
def test_retomada_requisita_so_as_paginas_que_faltam(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint)
    assert _paginas_em_disco(checkpoint) == ["acordaos_0001.json", "acordaos_0002.json"]

    for pagina in (3, 4):
        _register("acordaos", total=40, pagina=pagina)
    pasta = falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert Path(pasta) == checkpoint
    assert _paginas_pedidas() == [3, 4]
    assert _paginas_em_disco(checkpoint) == [f"acordaos_000{n}.json" for n in (1, 2, 3, 4)]
    assert len(falcao.listar_decisoes_parse(checkpoint)) == 4 * _POR_PAGINA


@responses.activate
def test_retomada_de_coleta_completa_nao_gasta_requisicao(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    for pagina in (1, 2):
        _register("acordaos", total=20, pagina=pagina)
    falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)
    responses.reset()

    df = falcao.listar_decisoes("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert len(responses.calls) == 0
    assert len(df) == 2 * _POR_PAGINA


@responses.activate
def test_listar_decisoes_retoma_e_mantem_o_checkpoint(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint, total=30)
    _register("acordaos", total=30, pagina=3)

    df = falcao.listar_decisoes("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [3]
    assert len(df) == 3 * _POR_PAGINA
    assert len(_paginas_em_disco(checkpoint)) == 3


@responses.activate
def test_retomada_com_paginas_explicitas_pula_as_gravadas(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint)
    _register("acordaos", total=40, pagina=4)

    falcao.listar_decisoes_download("dano moral", paginas=[2, 4], checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [4]


@responses.activate
def test_checkpoint_ocupado_nao_e_sobrescrito_por_coleta_nova(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint)

    with pytest.raises(ValueError, match="ocupado"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)

    assert len(responses.calls) == 0
    assert len(_paginas_em_disco(checkpoint)) == 2


@responses.activate
@pytest.mark.parametrize("mudanca", [
    {"pesquisa": "horas extras"},
    {"tribunais": "TST"},
    {"tamanho_pagina": 5},
    {"ordenacao": "mais_recente"},
])
def test_retomada_com_busca_diferente_falha_antes_de_requisitar(falcao, tmp_path, mudanca):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint)
    busca = {"pesquisa": "dano moral", **mudanca}

    with pytest.raises(ValueError, match="incompatível"):
        falcao.listar_decisoes_download(checkpoint_dir=checkpoint, resume=True, **busca)

    assert len(responses.calls) == 0


@responses.activate
def test_retomada_avisa_quando_o_total_muda_e_cobre_o_total_novo(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint, total=30)
    for pagina in (3, 4):
        _register("acordaos", total=40, pagina=pagina)

    with pytest.warns(UserWarning, match="mudou de 30 para 40"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [3, 4]
    assert json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8"))["total"] == 40


@responses.activate
def test_resume_sem_checkpoint_dir_falha_antes_de_requisitar(falcao):
    with pytest.raises(ValueError, match="resume=True exige checkpoint_dir"):
        falcao.listar_decisoes("dano moral", resume=True)
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("preparo", ["ausente", "sem_manifesto", "manifesto_invalido"])
def test_retomada_sem_checkpoint_valido_falha_antes_de_requisitar(falcao, tmp_path, preparo):
    checkpoint = tmp_path / "coleta"
    if preparo != "ausente":
        checkpoint.mkdir()
    if preparo == "manifesto_invalido":
        (checkpoint / "manifest.json").write_text("{", encoding="utf-8")

    with pytest.raises(ValueError, match="inexistente ou corrompido"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert len(responses.calls) == 0


@responses.activate
def test_checkpoint_dir_e_diretorio_juntos_levantam(falcao, tmp_path):
    with pytest.raises(ValueError, match=r"checkpoint_dir.*diretorio"):
        falcao.listar_decisoes_download(
            "dano moral", diretorio=str(tmp_path), checkpoint_dir=tmp_path / "coleta",
        )
    assert len(responses.calls) == 0


@responses.activate
def test_bloqueio_na_primeira_requisicao_deixa_checkpoint_retomavel(falcao, tmp_path):
    """Depois de uma chamada com checkpoint que falhou, ``resume=True`` sempre serve."""
    checkpoint = tmp_path / "coleta"
    _bloquear_por_cota()
    with pytest.raises(requests.HTTPError):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)
    responses.reset()
    _register("acordaos", total=10, pagina=1)

    falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [1]
    assert _paginas_em_disco(checkpoint) == ["acordaos_0001.json"]


@responses.activate
def test_resposta_sem_documentos_e_requisitada_de_novo(falcao, tmp_path):
    """Envelope de erro gravado não conta como página concluída."""
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint, total=30)
    (checkpoint / "acordaos_0002.json").write_text('{"userMessage": "erro"}', encoding="utf-8")
    for pagina in (2, 3):
        _register("acordaos", total=30, pagina=pagina)

    df = falcao.listar_decisoes("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [2, 3]
    assert len(df) == 3 * _POR_PAGINA


@responses.activate
def test_checkpoint_completo_nao_requisita_pagina_alem_do_total(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    for pagina in (1, 2):
        _register("acordaos", total=20, pagina=pagina)
    falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)
    responses.reset()

    falcao.listar_decisoes_download("dano moral", paginas=range(1, 6), checkpoint_dir=checkpoint, resume=True)

    assert len(responses.calls) == 0


@responses.activate
def test_retomada_de_checkpoint_completo_no_teto_repete_o_aviso(falcao, tmp_path, monkeypatch):
    monkeypatch.setattr("juscraper.aggregators.falcao.client._MAX_RESULTADOS", 20)
    checkpoint = tmp_path / "coleta"
    for pagina in (1, 2):
        _register("acordaos", total=20, pagina=pagina)
    with pytest.warns(UserWarning, match="teto"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint)
    responses.reset()

    with pytest.warns(UserWarning, match="teto"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert len(responses.calls) == 0


@responses.activate
def test_checkpoint_dir_que_e_arquivo_levanta_valueerror(falcao, tmp_path):
    arquivo = tmp_path / "coleta.json"
    arquivo.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="ocupado"):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=arquivo)
    assert len(responses.calls) == 0


@responses.activate
def test_pagina_interrompida_na_gravacao_e_requisitada_de_novo(falcao, tmp_path):
    """A sobra da gravação interrompida não passa por página concluída."""
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint, total=30)
    (checkpoint / "acordaos_0003.tmp").write_text('{"documentos": [', encoding="utf-8")
    _register("acordaos", total=30, pagina=3)

    df = falcao.listar_decisoes("dano moral", checkpoint_dir=checkpoint, resume=True)

    assert _paginas_pedidas() == [3]
    assert len(df) == 3 * _POR_PAGINA


@responses.activate
@pytest.mark.parametrize("paginas", [None, [1]])
@pytest.mark.parametrize("metodo", ["listar_decisoes", "listar_decisoes_download"])
def test_checkpoint_sem_ordenacao_coleta_por_data_e_nao_avisa(falcao, tmp_path, metodo, paginas):
    """As páginas do checkpoint se somam entre sessões, mesmo com ``paginas`` explícitas."""
    _register("acordaos", pagina=1, ordenacao="menos_recente")

    # filterwarnings=error: aviso viraria falha
    getattr(falcao, metodo)("dano moral", paginas=paginas, checkpoint_dir=tmp_path / "coleta")

    assert _paginas_pedidas() == [1]


@responses.activate
def test_retomada_sem_ordenacao_e_a_mesma_busca_de_menos_recente(falcao, tmp_path):
    checkpoint = tmp_path / "coleta"
    _interromper_na_pagina_3(falcao, checkpoint)
    for pagina in (3, 4):
        _register("acordaos", total=40, pagina=pagina, ordenacao="menos_recente")

    falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True, ordenacao="menos_recente")

    assert _paginas_pedidas() == [3, 4]


@responses.activate
@pytest.mark.parametrize("metodo", ["listar_decisoes", "listar_decisoes_download"])
def test_checkpoint_em_mais_relevante_avisa_uma_vez_que_ela_varia(falcao, tmp_path, metodo):
    """Medido ao vivo: a mesma página veio em três versões em três minutos."""
    for pagina in (1, 2):
        _register("acordaos", total=20, pagina=pagina, ordenacao="mais_relevante")

    with pytest.warns(UserWarning, match=f"{AVISO_DE_ORDEM}.*menos_recente") as avisos:
        getattr(falcao, metodo)("dano moral", checkpoint_dir=tmp_path / "coleta", ordenacao="mais_relevante")

    assert len(avisos) == 1
    assert _paginas_pedidas() == [1, 2]


@responses.activate
def test_checkpoint_em_mais_recente_nao_avisa(falcao, tmp_path):
    _register("acordaos", pagina=1, ordenacao="mais_recente")

    # filterwarnings=error: aviso viraria falha
    falcao.listar_decisoes_download("dano moral", checkpoint_dir=tmp_path / "coleta", ordenacao="mais_recente")


@responses.activate
def test_checkpoint_ocupado_falha_com_o_erro_do_diretorio_e_nao_com_o_aviso(falcao, tmp_path):
    _register("acordaos", pagina=1)
    falcao.listar_decisoes_download("dano moral", checkpoint_dir=tmp_path)

    with pytest.raises(ValueError, match="ocupado"):  # filterwarnings=error: aviso viraria falha
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=tmp_path, ordenacao="mais_relevante")


@responses.activate
def test_retomada_aceita_lista_de_filtro_em_outra_ordem(falcao, tmp_path):
    """A mesma lista em outra ordem é a mesma busca; a requisição segue a ordem passada."""
    checkpoint = tmp_path / "coleta"
    _register("acordaos", total=20, pagina=1, tribunais="TST,TRT3")
    _bloquear_por_cota()
    with pytest.raises(requests.HTTPError):
        falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, tribunais=["TST", "TRT3"])
    responses.reset()

    _register("acordaos", total=20, pagina=2, tribunais="TRT3,TST")
    falcao.listar_decisoes_download("dano moral", checkpoint_dir=checkpoint, resume=True, tribunais=["TRT3", "TST"])

    assert _paginas_pedidas() == [2]
