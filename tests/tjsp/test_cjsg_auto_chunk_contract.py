"""Offline contract tests for ``auto_chunk`` em TJSP cjsg (issue #130).

Mocka ``cjsg_download``/``cjsg_parse`` em vez de ``responses`` para isolar
o roteamento — o caminho HTTP normal já está coberto em
``test_cjsg_contract.py``. O foco aqui e o orquestrador:

* ``auto_chunk=False`` em janela > 366 dias preserva o ``ValueError`` antigo.
* Default em janela curta = 1 request (noop).
* Default em janela longa = N requests + dedup por ``cd_acordao``.
* ``auto_chunk=True`` + ``paginas != None`` em janela longa = ``ValueError``.
* ``auto_chunk=True`` + ``paginas != None`` em janela curta = ok (noop).
"""
import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjsp.client import TJSPScraper


def _patch_pipeline(mocker, parse_side_effect=None, parse_return=None):
    """Mock cjsg_download (path) + cjsg_parse (DataFrame) + shutil.rmtree."""
    download = mocker.patch.object(TJSPScraper, "cjsg_download", return_value="/fake/path")
    if parse_side_effect is not None:
        parse = mocker.patch.object(TJSPScraper, "cjsg_parse", side_effect=parse_side_effect)
    else:
        parse = mocker.patch.object(
            TJSPScraper,
            "cjsg_parse",
            return_value=parse_return if parse_return is not None
            else pd.DataFrame({"cd_acordao": ["x"]}),
        )
    mocker.patch("juscraper.courts._esaj.base.shutil.rmtree")
    return download, parse


def test_auto_chunk_false_long_window_raises(tmp_path):
    """``auto_chunk=False`` mantém o gate antigo (ValueError em > 366 dias)."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="no máximo 366"):
        scraper.cjsg(
            "dano moral",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
            auto_chunk=False,
        )


def test_auto_chunk_default_short_window_is_noop(tmp_path, mocker):
    """Default + janela curta = 1 chamada a cjsg_download (sem chunking)."""
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    df = scraper.cjsg(
        "dano moral",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 1
    assert list(df["cd_acordao"]) == ["x"]


def test_auto_chunk_default_long_window_chunks_and_dedups(tmp_path, mocker):
    """Default + janela longa = N chamadas + dedup por cd_acordao."""
    counter = {"i": 0}

    def fake_parse(_path):
        counter["i"] += 1
        return pd.DataFrame({"cd_acordao": [f"unico-{counter['i']}", "compartilhado"]})

    download, _ = _patch_pipeline(mocker, parse_side_effect=fake_parse)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    df = scraper.cjsg(
        "dano moral",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",  # ~3 anos → 3 janelas
    )

    assert download.call_count == 3
    # 3 únicos + 1 "compartilhado" (dedup remove duplicatas das janelas 2 e 3)
    assert len(df) == 4
    assert (df["cd_acordao"] == "compartilhado").sum() == 1


def test_auto_chunk_default_long_window_with_paginas_raises(tmp_path):
    """``auto_chunk=True`` + ``paginas != None`` + janela longa = ValueError."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="auto_chunk.*paginas"):
        scraper.cjsg(
            "dano moral",
            paginas=range(1, 3),
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )


def test_auto_chunk_default_short_window_with_paginas_ok(tmp_path, mocker):
    """Default + janela curta + paginas: chunking é noop, paginas funciona."""
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    df = scraper.cjsg(
        "dano moral",
        paginas=range(1, 3),
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 1
    assert list(df["cd_acordao"]) == ["x"]
    # paginas chega no cjsg_download (não foi descartado pelo orquestrador).
    download.assert_called_once()
    _, kwargs = download.call_args
    assert kwargs["paginas"] == range(1, 3)
