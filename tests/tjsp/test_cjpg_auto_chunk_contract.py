"""Offline contract tests for ``auto_chunk`` em TJSP cjpg (issue #130).

Mesma estrutura de ``test_cjsg_auto_chunk_contract.py``, com dedup por
``id_processo`` (chave canônica do parser cjpg, vide
``tjsp/cjpg_parse.py``).
"""
import warnings

import pandas as pd
import pytest

import juscraper as jus
from juscraper.courts.tjsp.client import TJSPScraper
from tests._helpers import assert_unknown_kwarg_raises


def _patch_pipeline(mocker, parse_side_effect=None, parse_return=None):
    download = mocker.patch.object(TJSPScraper, "cjpg_download", return_value="/fake/path")
    if parse_side_effect is not None:
        parse = mocker.patch.object(TJSPScraper, "cjpg_parse", side_effect=parse_side_effect)
    else:
        parse = mocker.patch.object(
            TJSPScraper,
            "cjpg_parse",
            return_value=parse_return if parse_return is not None
            else pd.DataFrame({"id_processo": ["x"]}),
        )
    mocker.patch("juscraper.courts.tjsp.client.shutil.rmtree")
    return download, parse


def test_auto_chunk_false_long_window_raises(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="no máximo 366"):
        scraper.cjpg(
            "dano moral",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
            auto_chunk=False,
        )


def test_auto_chunk_default_short_window_is_noop(tmp_path, mocker):
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    df = scraper.cjpg(
        "dano moral",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 1
    assert list(df["id_processo"]) == ["x"]


def test_auto_chunk_default_long_window_chunks_and_dedups(tmp_path, mocker):
    counter = {"i": 0}

    def fake_parse(_path):
        counter["i"] += 1
        return pd.DataFrame({"id_processo": [f"proc-{counter['i']}", "shared"]})

    download, _ = _patch_pipeline(mocker, parse_side_effect=fake_parse)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    df = scraper.cjpg(
        "dano moral",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 3
    assert len(df) == 4
    assert (df["id_processo"] == "shared").sum() == 1


def test_auto_chunk_default_long_window_with_paginas_raises(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    with pytest.raises(ValueError, match="auto_chunk.*paginas"):
        scraper.cjpg(
            "dano moral",
            paginas=range(1, 3),
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )


def test_auto_chunk_default_short_window_with_paginas_ok(tmp_path, mocker):
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cjpg(
        "dano moral",
        paginas=range(1, 3),
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    assert download.call_count == 1
    _, kwargs = download.call_args
    assert kwargs["paginas"] == range(1, 3)


def test_sniff_emite_um_deprecation_por_alias_no_caminho_noop(tmp_path, mocker):
    """Cada alias passado vira exatamente 1 ``DeprecationWarning`` (não 2).

    Antes do fix do auto-fill (refs bug TJSP cjpg), o ``run_auto_chunk``
    silenciava o sniff e o ``cjpg_download`` downstream emitia. Com o
    auto-fill, o caminho noop absorve aliases (para evitar duplicação do
    ``UserWarning`` de auto-fill) e re-emite manualmente o
    ``DeprecationWarning``. Resultado observável pelo usuário continua
    sendo 1 warning por alias — só que agora a emissão acontece no
    ``run_auto_chunk`` e o downstream fica silencioso. Como
    ``cjpg_download`` está mockado, capturamos exatamente os warnings
    emitidos pelo ``run_auto_chunk``.
    """
    _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        scraper.cjpg(
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
    """`auto_chunk` nao deve aparecer nos kwargs propagados ao schema."""
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    scraper.cjpg(
        "dano moral",
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/12/2024",
    )

    download.assert_called_once()
    _, kwargs = download.call_args
    assert "auto_chunk" not in kwargs


def test_data_publicacao_long_window_raises_typeerror_immediately(tmp_path, mocker):
    """`data_publicacao_*` em TJSP cjpg + janela longa = TypeError imediato.

    InputCJPGTJSP nao herda DataPublicacaoMixin (TJSP cjpg nao suporta
    filtro por publicacao). Sem o sniff de schema upfront, o erro viria
    como N janelas falhando em UserWarning. Com o sniff, vira TypeError
    limpo antes de qualquer chamada a cjpg_download.
    """
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    assert_unknown_kwarg_raises(
        scraper.cjpg,
        "data_publicacao_inicio",
        "dano moral",
        valor="01/03/2023",
        data_julgamento_inicio="01/01/2022",
        data_julgamento_fim="31/12/2024",  # > 366 dias -> chunked
    )

    download.assert_not_called()


def test_pesquisa_plus_query_alias_long_window_raises(tmp_path, mocker):
    """Conflito ``pesquisa`` + alias ``query`` no caminho chunked = ValueError.

    Mesmo gate testado em ``test_cjsg_auto_chunk_contract.py``: sem o
    ``normalize_pesquisa`` no orquestrador, o alias seria descartado
    silentemente e o caminho chunked divergiria do noop (que levanta
    ``ValueError`` via ``cjpg_download``).
    """
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.raises(ValueError, match="'pesquisa'.*'query'"):
        scraper.cjpg(
            "dano moral",
            query="outra coisa",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )

    download.assert_not_called()


def test_query_alias_only_long_window_works(tmp_path, mocker):
    """`cjpg(query="x")` (sem ``pesquisa``) em janela longa: alias funciona.

    cjpg admite ``pesquisa=""`` por default, entao o orquestrador deve
    chamar ``normalize_pesquisa`` com ``pesquisa or None`` para evitar
    falso positivo de conflito quando so o alias foi passado.
    """
    counter = {"i": 0}

    def fake_parse(_path):
        counter["i"] += 1
        return pd.DataFrame({"id_processo": [f"proc-{counter['i']}"]})

    download, _ = _patch_pipeline(mocker, parse_side_effect=fake_parse)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        df = scraper.cjpg(
            query="dano moral",
            data_julgamento_inicio="01/01/2022",
            data_julgamento_fim="31/12/2024",
        )

    assert download.call_count == 3
    assert len(df) == 3


# --- Auto-fill de data parcial (refs bug TJSP cjpg) --------------------------
# Antes: o backend eSAJ recebia ``dadosConsulta.dtFim=`` vazio quando o
# usuário passava só ``data_julgamento_inicio`` e devolvia "tudo desde X até
# hoje", fazendo o paginador iterar sobre dezenas de milhares de páginas.
# Agora: o pipeline autopreenche a data faltante (``_fim=hoje`` ou
# ``_inicio=01/01/1990``) e emite ``UserWarning``.


def test_cjpg_so_data_inicio_autopreenche_fim_com_hoje(tmp_path, mocker):
    """Só ``data_julgamento_inicio`` → ``cjpg_download`` recebe ``_fim=hoje``."""
    from datetime import date as _date
    download, _ = _patch_pipeline(mocker)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=r"data_julgamento_fim"):
        scraper.cjpg("dano moral", data_julgamento_inicio="01/04/2026")

    download.assert_called_once()
    _, kwargs = download.call_args
    # Janela curta (~33 dias) cabe em 1 chunk → caminho noop, kwargs
    # carregam a data autopreenchida explicitamente.
    hoje = _date.today().strftime("%d/%m/%Y")
    assert kwargs["data_julgamento_inicio"] == "01/04/2026"
    assert kwargs["data_julgamento_fim"] == hoje


def test_cjpg_so_data_fim_dispara_auto_chunk_de_1990(tmp_path, mocker):
    """Só ``data_julgamento_fim`` → auto-fill ``_inicio=01/01/1990`` + auto-chunk."""
    counter = {"i": 0}

    def fake_parse(_path):
        counter["i"] += 1
        return pd.DataFrame({"id_processo": [f"proc-{counter['i']}"]})

    download, _ = _patch_pipeline(mocker, parse_side_effect=fake_parse)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with pytest.warns(UserWarning, match=r"01/01/1990"):
        df = scraper.cjpg("dano moral", data_julgamento_fim="31/12/1991")

    # 01/01/1990 → 31/12/1991 = ~728 dias = 2 chunks de 366 dias.
    assert download.call_count == 2
    assert len(df) == 2
