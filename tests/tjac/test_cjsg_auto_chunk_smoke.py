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


def test_data_publicacao_reinjected_in_each_window(tmp_path, mocker):
    """`data_publicacao_*` deve aparecer nos kwargs de cada janela do chunked.

    Probe empirico (TJAC cjsg, 2026-04) confirmou que o backend AND'a
    julgamento + publicacao. Sem re-injetar, o filtro de publicacao seria
    silenciosamente descartado quando o usuario combina janela longa de
    julgamento com filtro curto de publicacao.
    """
    download = mocker.patch.object(TJACScraper, "cjsg_download", return_value="/fake/path")
    mocker.patch.object(TJACScraper, "cjsg_parse", return_value=pd.DataFrame({"cd_acordao": ["x"]}))
    mocker.patch("juscraper.courts._esaj.base.shutil.rmtree")

    scraper = jus.scraper("tjac", download_path=str(tmp_path))
    scraper.cjsg(
        "dano moral",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",  # ~3 anos -> 3 janelas
        data_publicacao_inicio="01/03/2023",
        data_publicacao_fim="30/06/2023",
    )

    assert download.call_count == 3
    # As 3 chamadas preservam os filtros de publicacao na integra.
    for call in download.call_args_list:
        kwargs = call.kwargs
        assert kwargs.get("data_publicacao_inicio") == "01/03/2023"
        assert kwargs.get("data_publicacao_fim") == "30/06/2023"
