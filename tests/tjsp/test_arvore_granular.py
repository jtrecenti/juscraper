"""Testes granulares do parser de arvores eSAJ (``parse_arvore``).

Exercita diretamente :func:`juscraper.courts._esaj.parse.parse_arvore` contra
a fixture enxuta ``tjsp/samples/arvore/classes_min.html``, cobrindo as bordas:
raiz, no intermediario, folha, nome acentuado, nome com hifen e a hierarquia
derivada do aninhamento ``<ul>/<li>``. Refs #228.
"""
import pandas as pd

from juscraper.courts._esaj.parse import parse_arvore
from tests._helpers import load_sample

ARVORE_COLUNAS = {"id", "nome", "id_pai", "nivel", "selecionavel", "caminho"}


def _df() -> pd.DataFrame:
    return parse_arvore(load_sample("tjsp", "arvore/classes_min.html"))


def test_colunas_exatas():
    df = _df()
    assert set(df.columns) == ARVORE_COLUNAS
    assert len(df) == 5


def _row(df: pd.DataFrame, node_id: str) -> dict:
    return dict(df.loc[df["id"] == node_id].iloc[0].to_dict())


def test_raiz_sem_pai():
    raiz = _row(_df(), "268")
    assert raiz["id_pai"] is None
    assert raiz["nivel"] == 1
    assert raiz["selecionavel"] is False
    assert raiz["caminho"] == "PROCESSO CRIMINAL"


def test_no_intermediario_nao_selecionavel():
    inter = _row(_df(), "308")
    assert inter["id_pai"] == "268"
    assert inter["nivel"] == 2
    assert inter["selecionavel"] is False


def test_folha_selecionavel_com_pai_correto():
    folha = _row(_df(), "14734")
    assert folha["selecionavel"] is True
    assert folha["id_pai"] == "308"
    assert folha["nivel"] == 3


def test_acentos_e_hifen_preservados_no_nome():
    folha = _row(_df(), "14734")
    assert folha["nome"] == "Medidas Protetivas - Criança e Adolescente (Lei 13.431)"


def test_caminho_lista_ancestrais_ate_o_no():
    folha = _row(_df(), "14734")
    assert folha["caminho"] == (
        "PROCESSO CRIMINAL > Medidas Cautelares > "
        "Medidas Protetivas - Criança e Adolescente (Lei 13.431)"
    )


def test_folha_na_raiz():
    # No selecionavel que tambem e raiz (sem pai, nivel 1).
    folha_raiz = _row(_df(), "5000")
    assert folha_raiz["id_pai"] is None
    assert folha_raiz["nivel"] == 1
    assert folha_raiz["selecionavel"] is True
    assert folha_raiz["nome"] == "Interpelação"


def test_html_vazio_retorna_df_com_colunas():
    df = parse_arvore("<div></div>")
    assert df.empty
    assert set(df.columns) == ARVORE_COLUNAS
