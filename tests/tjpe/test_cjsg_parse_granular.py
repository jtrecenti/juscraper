"""Testes granulares do parser do cjsg do TJPE sobre samples reais."""
from __future__ import annotations

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


def test_decisao_sem_ementa_sai_ausente():
    """Monocrática, sem o rótulo ``Ementa`` no bloco, sai com ementa ausente.

    A coluna existe mesmo quando a busca só traz monocráticas, e a mistura com
    acórdãos (parse de páginas dos dois tipos) mantém o texto destes.
    """
    paginas = [load_sample("tjpe", sample) for sample in SAMPLES]
    blocos = [rotulos for pagina in paginas for rotulos in _rotulos_por_bloco(pagina)]

    df = cjsg_parse(paginas)

    assert len(df) == len(blocos) == 15
    for ementa, rotulos in zip(df["ementa"], blocos, strict=True):
        if "Ementa" in rotulos:
            assert isinstance(ementa, str)
            assert ementa
        else:
            assert pd.isna(ementa)
            assert "Decisão" in rotulos
    assert df["ementa"].isna().sum() == 10


def test_so_monocraticas_tem_coluna_ementa_na_ordem_dos_acordaos():
    """Só com monocráticas, ``ementa`` existe e fica onde fica nos acórdãos."""
    df = cjsg_parse([load_sample("tjpe", "cjsg/monocraticas_resultado.html")])
    acordaos = cjsg_parse([load_sample("tjpe", "cjsg/simples_resultado.html")])

    assert df["ementa"].map(pd.isna).all()
    assert list(df.columns) == [c for c in acordaos.columns if c in df.columns]
