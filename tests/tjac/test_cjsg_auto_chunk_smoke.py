"""Smoke test for ``auto_chunk`` em TJAC cjsg (issue #130).

A logica de auto-chunking vive em ``EsajSearchScraper.cjsg`` (familia
compartilhada). Os contratos detalhados estao em
``tests/tjsp/test_cjsg_auto_chunk_contract.py`` — este arquivo so garante
que pelo menos um tribunal eSAJ nao-TJSP roteia pelo mesmo path sem
regressao silenciosa.
"""
import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjac.client import TJACScraper


def _patch_pipeline(mocker):
    download = mocker.patch.object(TJACScraper, "cjsg_download", return_value="/fake/path")
    mocker.patch.object(TJACScraper, "cjsg_parse", return_value=pd.DataFrame({"cd_acordao": ["x"]}))
    mocker.patch("juscraper.courts._esaj.base.shutil.rmtree")
    return download


def test_auto_chunk_default_long_window_chunks(tmp_path, mocker):
    """Default + janela longa = N requests + dedup (path compartilhado eSAJ)."""
    counter = {"i": 0}

    def fake_parse(_path):
        counter["i"] += 1
        return pd.DataFrame({"cd_acordao": [f"only-{counter['i']}", "shared"]})

    download = mocker.patch.object(TJACScraper, "cjsg_download", return_value="/fake/path")
    mocker.patch.object(TJACScraper, "cjsg_parse", side_effect=fake_parse)
    mocker.patch("juscraper.courts._esaj.base.shutil.rmtree")

    scraper = jus.scraper("tjac", download_path=str(tmp_path))
    df = scraper.cjsg(
        "dano moral",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 3
    # 3 unicos + 1 shared (dedup remove copias das janelas 2 e 3)
    assert len(df) == 4
    assert (df["cd_acordao"] == "shared").sum() == 1


def test_auto_chunk_false_long_window_raises(tmp_path):
    """`auto_chunk=False` mantem o gate antigo no caminho compartilhado."""
    scraper = jus.scraper("tjac", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="no máximo 366"):
        scraper.cjsg(
            "dano moral",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
            auto_chunk=False,
        )
