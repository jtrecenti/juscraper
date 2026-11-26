"""Testes granulares do parser do cjsg do TJPE sobre samples reais."""
from __future__ import annotations

from datetime import date

import pandas as pd
from bs4 import BeautifulSoup

from juscraper.courts.tjpe.parse import cjsg_parse
from tests._helpers import load_sample

# Uma página de acórdãos e as duas de monocráticas, capturadas ao vivo.
SAMPLES = (
    "cjsg/simples_resultado.html",
    "cjsg/monocraticas_resultado.html",
    "cjsg/monocraticas_pagina_02.xml",
)


def _rotulos_por_bloco(html: str) -> list[set[str]]:
    soup = BeautifulSoup(html, "html.parser")
    return [
        {label.get_text(strip=True) for label in tabela.find_all("label")}
        for tabela in soup.find_all("table", class_="tableDocumento")
    ]


def test_monocratica_sem_ementa_com_data_de_publicacao_e_decisao():
    """Monocrática sai com ementa ausente, ``data_publicacao`` e o texto em ``decisao``.

    O bloco das monocráticas não tem ``Ementa`` e traz ``Data da Publicação`` e
    ``Decisão``; o dos acórdãos traz ``Ementa``, ``Data da Publicação/Fonte`` e
    ``Acórdão``. A mistura dos dois (parse de páginas dos dois tipos) mantém o
    texto de cada um, com o do outro ausente.
    """
    paginas = [load_sample("tjpe", sample) for sample in SAMPLES]
    blocos = [rotulos for pagina in paginas for rotulos in _rotulos_por_bloco(pagina)]

    df = cjsg_parse(paginas)

    assert len(df) == len(blocos) == 15
    assert df["data_publicacao"].map(lambda d: isinstance(d, date)).all()
    for (_, linha), rotulos in zip(df.iterrows(), blocos, strict=True):
        if "Decisão" in rotulos:
            assert pd.isna(linha["ementa"])
            assert pd.isna(linha["acordao"])
            assert isinstance(linha["decisao"], str)
            assert linha["decisao"]
        else:
            assert "Ementa" in rotulos
            assert isinstance(linha["ementa"], str)
            assert linha["ementa"]
            assert isinstance(linha["acordao"], str)
            assert pd.isna(linha["decisao"])
    assert df["decisao"].notna().sum() == 10


def test_so_monocraticas_tem_colunas_na_ordem_dos_acordaos():
    """Só com monocráticas, ``ementa`` existe e as colunas seguem a ordem dos acórdãos.

    ``decisao``, que só as monocráticas têm, fica onde ``acordao`` fica nos
    acórdãos: depois de ``ementa`` e antes de ``meio_tramitacao``.
    """
    df = cjsg_parse([load_sample("tjpe", "cjsg/monocraticas_resultado.html")])

    assert df["ementa"].map(pd.isna).all()
    assert list(df.columns) == [
        "processo", "classe", "assunto", "relator", "data_publicacao",
        "ementa", "decisao", "meio_tramitacao", "url_inteiro_teor",
    ]
    assert df.loc[0, "data_publicacao"] == date(2023, 11, 1)
    assert df.loc[0, "decisao"].startswith("À unanimidade de votos")
