"""Characterization tests for the shared eSAJ ``run_auto_chunk`` helper."""
import warnings
from unittest.mock import Mock

import pandas as pd
import pytest
from pydantic import ValidationError

from juscraper.courts._esaj.base import run_auto_chunk
from juscraper.courts._esaj.schemas import InputCJSGEsajPuro
from juscraper.courts.tjsp.schemas import InputCJPGTJSP


def _deprecation_messages(caught: list[warnings.WarningMessage]) -> list[str]:
    return [
        str(warning.message)
        for warning in caught
        if issubclass(warning.category, DeprecationWarning)
    ]


def test_disabled_auto_chunk_only_removes_control_flag():
    fetch = Mock()
    kwargs = {
        "auto_chunk": False,
        "data_inicio": "01/01/2022",
        "unknown_filter": "preserved",
    }

    result = run_auto_chunk(
        method=fetch,
        method_label="TJSPScraper.cjpg()",
        input_cls=InputCJPGTJSP,
        dedup_key="id_processo",
        pesquisa="dano moral",
        paginas=None,
        kwargs=kwargs,
    )

    assert result is None
    assert kwargs == {
        "data_inicio": "01/01/2022",
        "unknown_filter": "preserved",
    }
    fetch.assert_not_called()


def test_short_window_canonicalizes_date_aliases_and_warns_once():
    fetch = Mock()
    kwargs = {
        "auto_chunk": True,
        "data_inicio": "2024-01-01",
        "data_fim": "2024-01-31",
        "marker": "preserved",
    }

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_auto_chunk(
            method=fetch,
            method_label="TJSPScraper.cjpg()",
            input_cls=InputCJPGTJSP,
            dedup_key="id_processo",
            pesquisa="dano moral",
            paginas=None,
            kwargs=kwargs,
        )

    deprecations = [
        warning for warning in caught
        if issubclass(warning.category, DeprecationWarning)
    ]
    assert result is None
    assert kwargs == {
        "data_julgamento_inicio": "01/01/2024",
        "data_julgamento_fim": "31/01/2024",
        "marker": "preserved",
    }
    assert len(deprecations) == 2
    assert {str(warning.message).split("'")[1] for warning in deprecations} == {
        "data_inicio",
        "data_fim",
    }
    fetch.assert_not_called()


def test_long_window_removes_dates_from_kwargs_and_reinjects_filters():
    fetch = Mock(return_value=pd.DataFrame({"cd_acordao": ["shared"]}))
    kwargs = {
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
        "data_publicacao_inicio": "01/03/2023",
        "data_publicacao_fim": "30/06/2023",
        "origem": "R",
    }

    result = run_auto_chunk(
        method=fetch,
        method_label="TJACScraper.cjsg()",
        input_cls=InputCJSGEsajPuro,
        dedup_key="cd_acordao",
        pesquisa="dano moral",
        paginas=None,
        kwargs=kwargs,
    )

    assert kwargs == {"origem": "R"}
    assert fetch.call_count == 3
    assert result.to_dict("records") == [{"cd_acordao": "shared"}]
    for call in fetch.call_args_list:
        assert call.kwargs["pesquisa"] == "dano moral"
        assert call.kwargs["paginas"] is None
        assert call.kwargs["auto_chunk"] is False
        assert call.kwargs["data_publicacao_inicio"] == "01/03/2023"
        assert call.kwargs["data_publicacao_fim"] == "30/06/2023"
        assert call.kwargs["origem"] == "R"


def test_empty_search_is_valid_for_cjpg_long_window():
    fetch = Mock(return_value=pd.DataFrame({"id_processo": ["shared"]}))
    kwargs = {
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
        "classe": "12728",
    }

    result = run_auto_chunk(
        method=fetch,
        method_label="TJSPScraper.cjpg()",
        input_cls=InputCJPGTJSP,
        dedup_key="id_processo",
        pesquisa="",
        paginas=None,
        kwargs=kwargs,
    )

    assert kwargs == {"classe": "12728"}
    assert fetch.call_count == 3
    assert result.to_dict("records") == [{"id_processo": "shared"}]
    assert {call.kwargs["pesquisa"] for call in fetch.call_args_list} == {""}


@pytest.mark.parametrize("alias", ["query", "termo"])
def test_search_alias_supplies_every_long_window_and_warns_once(alias):
    fetch = Mock(return_value=pd.DataFrame({"id_processo": ["shared"]}))
    kwargs = {
        alias: "dano moral pelo alias",
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
    }

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_auto_chunk(
            method=fetch,
            method_label="TJSPScraper.cjpg()",
            input_cls=InputCJPGTJSP,
            dedup_key="id_processo",
            pesquisa="",
            paginas=None,
            kwargs=kwargs,
        )

    messages = _deprecation_messages(caught)
    assert messages == [
        f"O parâmetro '{alias}' está deprecado. Use 'pesquisa' em vez disso."
    ]
    assert kwargs == {}
    assert fetch.call_count == 3
    assert result.to_dict("records") == [{"id_processo": "shared"}]
    assert {
        call.kwargs["pesquisa"] for call in fetch.call_args_list
    } == {"dano moral pelo alias"}


@pytest.mark.parametrize(
    ("input_cls", "dedup_key", "date_kwargs", "aliases"),
    [
        (
            InputCJPGTJSP,
            "id_processo",
            {
                "data_inicio": "01/01/2022",
                "data_fim": "31/12/2024",
            },
            {"data_inicio", "data_fim"},
        ),
        (
            InputCJPGTJSP,
            "id_processo",
            {
                "data_julgamento_de": "01/01/2022",
                "data_julgamento_ate": "31/12/2024",
            },
            {"data_julgamento_de", "data_julgamento_ate"},
        ),
        (
            InputCJSGEsajPuro,
            "cd_acordao",
            {
                "data_julgamento_inicio": "01/01/2022",
                "data_julgamento_fim": "31/12/2024",
                "data_publicacao_de": "01/03/2023",
                "data_publicacao_ate": "30/06/2023",
            },
            {"data_publicacao_de", "data_publicacao_ate"},
        ),
    ],
)
def test_long_window_date_aliases_warn_once_and_are_not_repropagated(
    input_cls,
    dedup_key,
    date_kwargs,
    aliases,
):
    fetch = Mock(return_value=pd.DataFrame({dedup_key: ["shared"]}))
    kwargs = date_kwargs.copy()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = run_auto_chunk(
            method=fetch,
            method_label="EsajSearchScraper.cjsg()",
            input_cls=input_cls,
            dedup_key=dedup_key,
            pesquisa="dano moral",
            paginas=None,
            kwargs=kwargs,
        )

    messages = _deprecation_messages(caught)
    assert len(messages) == len(aliases)
    assert all(sum(f"'{alias}'" in message for message in messages) == 1 for alias in aliases)
    assert kwargs == {}
    assert fetch.call_count == 3
    assert result.to_dict("records") == [{dedup_key: "shared"}]


def test_invalid_known_filter_remains_validation_error_before_fetch():
    fetch = Mock()
    kwargs = {
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
        "origem": "invalid",
    }

    with pytest.raises(ValidationError) as exc_info:
        run_auto_chunk(
            method=fetch,
            method_label="TJACScraper.cjsg()",
            input_cls=InputCJSGEsajPuro,
            dedup_key="cd_acordao",
            pesquisa="dano moral",
            paginas=None,
            kwargs=kwargs,
        )

    assert {error["type"] for error in exc_info.value.errors()} == {"literal_error"}
    assert kwargs == {"origem": "invalid"}
    fetch.assert_not_called()


def test_only_pure_extra_forbidden_validation_becomes_type_error():
    fetch = Mock()
    kwargs = {
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
        "unknown_filter": "invalid",
    }

    with pytest.raises(TypeError, match="unknown_filter"):
        run_auto_chunk(
            method=fetch,
            method_label="TJACScraper.cjsg()",
            input_cls=InputCJSGEsajPuro,
            dedup_key="cd_acordao",
            pesquisa="dano moral",
            paginas=None,
            kwargs=kwargs,
        )

    assert kwargs == {"unknown_filter": "invalid"}
    fetch.assert_not_called()


def test_mixed_extra_and_known_validation_errors_remain_validation_error():
    fetch = Mock()
    kwargs = {
        "data_julgamento_inicio": "01/01/2022",
        "data_julgamento_fim": "31/12/2024",
        "origem": "invalid",
        "unknown_filter": "invalid",
    }

    with pytest.raises(ValidationError) as exc_info:
        run_auto_chunk(
            method=fetch,
            method_label="TJACScraper.cjsg()",
            input_cls=InputCJSGEsajPuro,
            dedup_key="cd_acordao",
            pesquisa="dano moral",
            paginas=None,
            kwargs=kwargs,
        )

    assert {error["type"] for error in exc_info.value.errors()} == {
        "extra_forbidden",
        "literal_error",
    }
    assert kwargs == {
        "origem": "invalid",
        "unknown_filter": "invalid",
    }
    fetch.assert_not_called()
