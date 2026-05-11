"""Offline contract tests for ``auto_chunk`` em TJSP cjsg (issue #130).

Mocka ``cjsg_download``/``cjsg_parse`` em vez de ``responses`` para isolar
o roteamento — o caminho HTTP normal já está coberto em
``test_cjsg_contract.py``. O foco aqui e o orquestrador:

* ``auto_chunk=False`` em janela > 366 dias preserva o ``ValueError`` antigo.
* Default em janela curta = 1 request (noop).
* Default em janela longa = N requests + dedup por ``cd_acordao``.
* ``auto_chunk=True`` + ``paginas != None`` em janela longa = ``ValueError``.
* ``auto_chunk=True`` + ``paginas != None`` em janela curta = ok (noop).
* Aliases deprecados (``data_inicio``/``data_fim``) emitem ``DeprecationWarning``
  uma unica vez no caminho noop (sniff suprime).
* ``auto_chunk`` nao vaza para o schema validator no caminho noop.
"""
import warnings

import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjsp.client import TJSPScraper
from tests._helpers import assert_unknown_kwarg_raises


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


def test_sniff_emite_um_deprecation_por_alias_no_caminho_noop(tmp_path, mocker):
    """Cada alias passado vira exatamente 1 ``DeprecationWarning`` (não 2).

    Antes do auto-fill, o ``run_auto_chunk`` silenciava o sniff e o
    ``cjsg_download`` downstream emitia. Com o auto-fill (refs bug TJSP
    cjpg), o caminho noop absorve aliases para evitar duplicação do
    ``UserWarning`` e re-emite manualmente o ``DeprecationWarning``.
    O efeito observável continua sendo 1 warning por alias — só muda
    a fonte. Como ``cjsg_download`` está mockado, capturamos exatamente
    os warnings do ``run_auto_chunk``.
    """
    _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        scraper.cjsg(
            "dano moral",
            data_inicio="01/01/2024",
            data_fim="31/12/2024",
        )

    deprecation_warnings = [
        warning for warning in w
        if issubclass(warning.category, DeprecationWarning)
    ]
    aliases_passados = {"data_inicio", "data_fim"}
    mensagens = [str(warning.message) for warning in deprecation_warnings]
    for alias in aliases_passados:
        assert sum(1 for m in mensagens if f"'{alias}'" in m) == 1, (
            f"Esperado exatamente 1 DeprecationWarning para '{alias}', "
            f"recebido: {mensagens}"
        )


def test_auto_chunk_not_propagated_to_download(tmp_path, mocker):
    """`auto_chunk` nao deve aparecer nos kwargs propagados ao schema.

    No caminho noop, `cjsg_download` valida via pydantic. Mesmo com o
    `AutoChunkMixin` aceitando o flag, manter a flag fora dos kwargs e
    preferivel: o flag nao tem semantica downstream.
    """
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cjsg(
        "dano moral",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    download.assert_called_once()
    _, kwargs = download.call_args
    assert "auto_chunk" not in kwargs


def test_data_publicacao_long_window_raises_typeerror_immediately(tmp_path, mocker):
    """`data_publicacao_*` em TJSP cjsg + janela longa = TypeError imediato.

    InputCJSGTJSP nao herda DataPublicacaoMixin (TJSP nao suporta filtro
    por publicacao). Sem o sniff de schema upfront, o erro viria como N
    janelas falhando em UserWarning. Com o sniff, vira TypeError limpo
    antes de qualquer chamada a cjsg_download.
    """
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    assert_unknown_kwarg_raises(
        scraper.cjsg,
        "data_publicacao_inicio",
        "dano moral",
        valor="01/03/2023",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",  # > 366 dias -> chunked
    )

    download.assert_not_called()


def test_pesquisa_plus_query_alias_long_window_raises(tmp_path, mocker):
    """Conflito ``pesquisa`` + alias ``query`` no caminho chunked = ValueError.

    Sem o gate de ``normalize_pesquisa`` no orquestrador, o
    ``pop_normalize_aliases`` descartaria silentemente o alias e a busca
    rodaria so com ``pesquisa`` (regressao em relacao ao caminho noop, que
    levanta ``ValueError`` via ``cjsg_download``). O fix preserva o erro.
    """
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match="'pesquisa'.*'query'"):
        scraper.cjsg(
            "dano moral",
            query="outra coisa",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",  # > 366 dias -> chunked
        )

    download.assert_not_called()


def test_pesquisa_plus_termo_alias_long_window_raises(tmp_path, mocker):
    """Mesmo gate, mas com o alias ``termo``."""
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match="'pesquisa'.*'termo'"):
        scraper.cjsg(
            "dano moral",
            termo="outra coisa",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )

    download.assert_not_called()
