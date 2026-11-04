"""``download_path``: o diretório temporário só nasce quando alguém o lê.

Construir um raspador sem ``download_path`` não pode deixar diretório para
trás. Antes, toda construção chamava ``tempfile.mkdtemp()`` e nada removia o
resultado, mesmo quando o raspador nunca gravava nele.
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import pytest

import juscraper as jus
from juscraper import _SCRAPERS
from juscraper.core.base import BaseScraper


@pytest.fixture
def raiz_temporaria(tmp_path, monkeypatch):
    """Faz o ``tempfile`` criar tudo dentro de um diretório vazio e observável."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


def _criados(raiz: Path) -> list[str]:
    return sorted(item.name for item in raiz.iterdir())


@pytest.mark.parametrize("sigla", sorted(_SCRAPERS))
def test_construir_raspador_nao_cria_diretorio(raiz_temporaria, sigla):
    jus.scraper(sigla)

    assert _criados(raiz_temporaria) == []


@pytest.mark.parametrize("sigla", sorted(_SCRAPERS))
def test_primeira_leitura_cria_o_diretorio_e_as_seguintes_o_reusam(raiz_temporaria, sigla):
    raspador = jus.scraper(sigla)

    primeiro = raspador.download_path
    segundo = raspador.download_path

    assert Path(primeiro).is_dir()
    assert Path(primeiro).parent == raiz_temporaria
    assert segundo == primeiro
    assert len(_criados(raiz_temporaria)) == 1


def test_cada_raspador_recebe_o_proprio_diretorio(raiz_temporaria):
    um = jus.scraper("tjpi")
    outro = jus.scraper("tjpi")

    assert um.download_path != outro.download_path
    assert len(_criados(raiz_temporaria)) == 2


def test_caminho_informado_e_criado_na_construcao_e_nada_mais(raiz_temporaria):
    destino = raiz_temporaria / "meus" / "downloads"

    raspador = jus.scraper("tjpi", download_path=str(destino))

    assert destino.is_dir()
    assert raspador.download_path == str(destino)
    assert _criados(raiz_temporaria) == ["meus"]


def test_set_download_path_com_none_volta_a_criar_sob_demanda(raiz_temporaria):
    destino = raiz_temporaria / "fixo"
    raspador = jus.scraper("tjpi", download_path=str(destino))

    raspador.set_download_path(None)

    assert _criados(raiz_temporaria) == ["fixo"]
    assert Path(raspador.download_path).parent == raiz_temporaria
    assert raspador.download_path != str(destino)


def test_atribuicao_direta_continua_valendo(raiz_temporaria):
    raspador = jus.scraper("tjpi")

    raspador.download_path = "/caminho/escolhido"

    assert raspador.download_path == "/caminho/escolhido"
    assert _criados(raiz_temporaria) == []


@pytest.mark.usefixtures("raiz_temporaria")
def test_datajud_mantem_o_prefixo_do_diretorio():
    raspador = jus.scraper("datajud")

    assert Path(raspador.download_path).name.startswith("datajud_api_")


def test_tjsp_set_download_path_sem_argumento_troca_o_diretorio_sob_demanda(raiz_temporaria):
    raspador = jus.scraper("tjsp")
    anterior = raspador.download_path

    raspador.set_download_path()

    assert _criados(raiz_temporaria) == [Path(anterior).name]
    assert raspador.download_path != anterior
    assert len(_criados(raiz_temporaria)) == 2


def test_tjsp_nao_cria_o_caminho_informado(raiz_temporaria):
    # O TJSP sempre deixou a criação para os downloaders, que gravam em
    # subpastas do caminho. A base cria o caminho informado; o TJSP, não.
    destino = raiz_temporaria / "tjsp"

    raspador = jus.scraper("tjsp", download_path=str(destino))

    assert raspador.download_path == str(destino)
    assert not destino.exists()


def test_subclasse_direta_de_basescraper_tambem_cria_sob_demanda(raiz_temporaria):
    class Minimo(BaseScraper):
        """Subclasse que nunca chama ``set_download_path``."""

    raspador = Minimo("minimo")

    assert _criados(raiz_temporaria) == []
    assert Path(raspador.download_path).parent == raiz_temporaria
    assert Path(raspador.download_path).is_dir()


def test_threads_na_primeira_leitura_veem_o_mesmo_diretorio(raiz_temporaria, monkeypatch):
    # ``mkdtemp`` lento alarga a janela entre testar ``None`` e gravar o
    # caminho; sem trava, cada thread criaria o próprio diretório.
    original = tempfile.mkdtemp

    def mkdtemp_lento(*args, **kwargs):
        time.sleep(0.05)
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp_lento)
    raspador = jus.scraper("tjpi")
    largada = threading.Barrier(4)
    vistos: list[str] = []

    def ler():
        largada.wait()
        vistos.append(raspador.download_path)

    threads = [threading.Thread(target=ler) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(set(vistos)) == 1
    assert len(_criados(raiz_temporaria)) == 1
