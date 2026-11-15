"""Testes unitários da coluna ``tipo_decisao`` do parser cjsg do TJRR."""
from __future__ import annotations

import pytest
from bs4 import BeautifulSoup

from juscraper.courts.tjrr.download import _extract_cdata
from juscraper.courts.tjrr.parse import _TABELA_NO_ID_RE, cjsg_parse_manager
from tests._helpers import load_sample


def _linhas(sample: str) -> BeautifulSoup:
    return BeautifulSoup(_extract_cdata(load_sample("tjrr", f"cjsg/{sample}")), "html.parser")


@pytest.mark.parametrize(
    ("sample", "esperado"),
    [
        ("step_02_search.html", ["acordao"] * 10 + ["monocratica"] * 10),
        ("step_03_pagina_02.xml", ["acordao"] * 10),
        ("step_04_pagina_02_monocraticas.xml", ["monocratica"] * 10),
    ],
)
def test_tipo_decisao_pelo_id_dos_botoes(sample, esperado):
    df = cjsg_parse_manager([str(_linhas(sample))])
    assert df["tipo_decisao"].tolist() == esperado
    assert df.columns[-1] == "tipo_decisao"


def test_tipo_decisao_ausente_avisa():
    """Linha sem botão com o id da tabela: ``tipo_decisao`` fica ``None``, com aviso."""
    soup = _linhas("step_03_pagina_02.xml")
    for tag in soup.find_all(id=_TABELA_NO_ID_RE):
        del tag["id"]
    with pytest.warns(UserWarning, match="10 de 10 linha"):
        df = cjsg_parse_manager([str(soup)])
    assert df["tipo_decisao"].isna().all()
