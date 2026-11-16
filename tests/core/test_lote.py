"""Contratos do laço comum dos downloads em lote (``juscraper.core.lote``)."""
import logging

import pandas as pd
import pytest

from juscraper.core.download import ErroDeGravacaoError, gravar_arquivo
from juscraper.core.lote import DownloadEmLote, baixar_em_lote

LOTE = DownloadEmLote(
    origem="tabela",
    colunas=("codigo",),
    erros_com_motivo=(),
    coluna_caminho="caminho",
    descricao="download(s)",
    logger=logging.getLogger("juscraper.teste"),
    rotulo=lambda linha: str(linha.codigo),
)


def _baixar(erros: dict[int, Exception], pedidos: list[int]):
    def baixar(linha):
        pedidos.append(linha.codigo)
        if linha.codigo in erros:
            raise erros[linha.codigo]
        return f"/pasta/{linha.codigo}.pdf"

    return baixar


def test_erro_de_gravacao_vira_linha_e_encerra_o_lote():
    pedidos: list[int] = []
    tabela = pd.DataFrame({"codigo": [1, 2, 3]})
    erro = ErroDeGravacaoError(28, "No space left on device", "/pasta/2.pdf")

    with pytest.warns(UserWarning, match=r"2 download\(s\) falharam.*2: erro_de_gravacao"):
        df = baixar_em_lote(tabela, _baixar({2: erro}, pedidos), LOTE, "Raspador.baixar")

    # O que já foi baixado fica; a linha depois do erro de disco não é pedida.
    # Sem o embrulho do método público, o ausente da coluna de texto fica como o pandas o põe.
    assert df["caminho"].iloc[0] == "/pasta/1.pdf"
    assert df["caminho"].iloc[1:].isna().all()
    assert pd.isna(df["motivo_falha"].iloc[0])
    assert df["motivo_falha"].iloc[1:].tolist() == ["erro_de_gravacao"] * 2
    assert pedidos == [1, 2]


@pytest.mark.parametrize("erro", [OSError("Could not find a suitable TLS CA certificate bundle"), ValueError("x")])
def test_erro_que_nao_e_de_gravacao_continua_propagando(erro):
    # O ``requests`` levanta ``OSError`` puro para o arquivo de certificados que não existe.
    with pytest.raises(type(erro)):
        baixar_em_lote(pd.DataFrame({"codigo": [1, 2]}), _baixar({1: erro}, []), LOTE, "Raspador.baixar")


def test_gravar_arquivo_levanta_erro_de_gravacao_com_o_errno_original(tmp_path):
    destino = tmp_path / "a.pdf"
    destino.mkdir()

    with pytest.raises(ErroDeGravacaoError) as info:
        gravar_arquivo(b"%PDF", destino)

    assert isinstance(info.value.__cause__, IsADirectoryError)
    assert str(info.value) == str(info.value.__cause__)
    assert info.value.errno == info.value.__cause__.errno
    assert not (tmp_path / "a.tmp").exists()
