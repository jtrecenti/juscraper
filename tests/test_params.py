"""Tests for the parameter normalization utilities."""
import warnings

import pytest

from juscraper.utils.params import (
    normalize_datas,
    normalize_paginas,
    normalize_pesquisa,
    pop_deprecated_alias,
    resolve_deprecated_alias,
    validate_intervalo_datas,
    warn_unsupported,
)

# --- normalize_paginas ---

class TestNormalizePaginas:

    def test_none(self):
        assert normalize_paginas(None) is None

    def test_int(self):
        result = normalize_paginas(3)
        assert result == range(1, 4)

    def test_range_passthrough(self):
        r = range(2, 5)
        assert normalize_paginas(r) is r

    def test_list_passthrough(self):
        lst = [1, 3, 5]
        assert normalize_paginas(lst) is lst

    def test_invalid_type(self):
        with pytest.raises(TypeError, match="paginas deve ser"):
            normalize_paginas("abc")


# --- normalize_pesquisa ---

class TestNormalizePesquisa:

    def test_standard(self):
        assert normalize_pesquisa("teste") == "teste"

    def test_from_query_deprecated(self):
        kwargs = {"query": "teste"}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_pesquisa(**kwargs)
        assert result == "teste"
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "query" in str(w[0].message)

    def test_from_termo_deprecated(self):
        kwargs = {"termo": "teste"}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_pesquisa(**kwargs)
        assert result == "teste"
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "termo" in str(w[0].message)

    def test_conflict_pesquisa_and_query(self):
        with pytest.raises(ValueError, match="pesquisa.*query"):
            normalize_pesquisa(pesquisa="a", query="b")

    def test_conflict_pesquisa_and_termo(self):
        with pytest.raises(ValueError, match="pesquisa.*termo"):
            normalize_pesquisa(pesquisa="a", termo="b")

    def test_missing(self):
        with pytest.raises(TypeError, match="pesquisa"):
            normalize_pesquisa()



# --- normalize_datas ---

class TestNormalizeDatas:

    def test_standard_canonical(self):
        result = normalize_datas(
            data_julgamento_inicio="01/01/2023",
            data_julgamento_fim="31/12/2023",
        )
        assert result["data_julgamento_inicio"] == "01/01/2023"
        assert result["data_julgamento_fim"] == "31/12/2023"
        assert result["data_publicacao_inicio"] is None
        assert result["data_publicacao_fim"] is None

    def test_deprecated_de_ate(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_datas(
                data_julgamento_de="01/01/2023",
                data_julgamento_ate="31/12/2023",
            )
        assert result["data_julgamento_inicio"] == "01/01/2023"
        assert result["data_julgamento_fim"] == "31/12/2023"
        assert len(w) == 2
        assert all(issubclass(x.category, DeprecationWarning) for x in w)

    def test_generic_alias(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = normalize_datas(
                data_inicio="01/01/2023",
                data_fim="31/12/2023",
            )
        assert result["data_julgamento_inicio"] == "01/01/2023"
        assert result["data_julgamento_fim"] == "31/12/2023"
        assert len(w) == 2

    def test_conflict_generic_and_specific(self):
        with pytest.raises(ValueError, match="data_inicio.*data_julgamento_inicio"):
            normalize_datas(
                data_inicio="01/01/2023",
                data_julgamento_inicio="01/01/2023",
            )

    def test_conflict_deprecated_and_canonical(self):
        with pytest.raises(ValueError, match="data_julgamento_de.*data_julgamento_inicio"):
            normalize_datas(
                data_julgamento_de="01/01/2023",
                data_julgamento_inicio="01/01/2023",
            )

    def test_all_none(self):
        result = normalize_datas()
        assert all(v is None for v in result.values())

    def test_publicacao_dates(self):
        result = normalize_datas(
            data_publicacao_inicio="01/01/2023",
            data_publicacao_fim="31/12/2023",
        )
        assert result["data_publicacao_inicio"] == "01/01/2023"
        assert result["data_publicacao_fim"] == "31/12/2023"


# --- validate_intervalo_datas ---

class TestValidateIntervaloDatas:

    def test_both_none_skips(self):
        # No exception; returns None
        assert validate_intervalo_datas(None, None) is None

    def test_one_none_skips(self):
        assert validate_intervalo_datas("01/01/2023", None) is None
        assert validate_intervalo_datas(None, "31/12/2023") is None

    def test_one_year_exact_ok(self):
        # 365-day window passes with default max_dias=366.
        assert validate_intervalo_datas("01/01/2023", "01/01/2024") is None

    def test_one_year_across_leap_day_ok(self):
        # 2024 is a leap year — 01/01/2024 -> 01/01/2025 spans 366 days, still
        # a calendar year. Must not be rejected client-side.
        assert validate_intervalo_datas("01/01/2024", "01/01/2025") is None

    def test_same_day_ok(self):
        assert validate_intervalo_datas("15/06/2023", "15/06/2023") is None

    def test_over_one_year_raises(self):
        with pytest.raises(ValueError, match="no máximo 366 dias"):
            validate_intervalo_datas("01/01/2020", "31/12/2021")

    def test_rotulo_in_message(self):
        with pytest.raises(ValueError, match="data_julgamento_inicio"):
            validate_intervalo_datas(
                "01/01/2020",
                "31/12/2021",
                rotulo="data_julgamento",
            )

    def test_inicio_after_fim_raises(self):
        with pytest.raises(ValueError, match="posterior"):
            validate_intervalo_datas("31/12/2023", "01/01/2023")

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError, match="Formato esperado"):
            validate_intervalo_datas("2020-01-01", "31/12/2020")

    def test_invalid_fim_format_raises(self):
        with pytest.raises(ValueError, match="data_fim"):
            validate_intervalo_datas("01/01/2020", "2020-12-31", rotulo="data")

    def test_custom_max_dias(self):
        # 31 days allowed, 32 not.
        assert validate_intervalo_datas(
            "01/01/2023", "01/02/2023", max_dias=31
        ) is None
        with pytest.raises(ValueError, match="no máximo 31 dias"):
            validate_intervalo_datas(
                "01/01/2023", "02/02/2023", max_dias=31
            )

    def test_default_origem_esaj(self):
        with pytest.raises(ValueError, match="O eSAJ aceita no máximo"):
            validate_intervalo_datas("01/01/2020", "31/12/2021")

    def test_custom_origem(self):
        with pytest.raises(ValueError, match="O TJRS aceita no máximo"):
            validate_intervalo_datas(
                "01/01/2020", "31/12/2021", origem="O TJRS"
            )


# --- warn_unsupported ---

class TestWarnUnsupported:

    def test_emits_warning(self):
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_unsupported("data_julgamento_inicio", "TJDFT")
        assert len(w) == 1
        assert issubclass(w[0].category, UserWarning)
        assert "TJDFT" in str(w[0].message)
        assert "data_julgamento_inicio" in str(w[0].message)


# --- pop_deprecated_alias ---

class TestPopDeprecatedAlias:

    def test_absent_returns_none(self):
        kwargs = {"outro": "x"}
        assert pop_deprecated_alias(kwargs, "magistrado", "relator") is None
        assert kwargs == {"outro": "x"}

    def test_present_pops_and_warns(self):
        kwargs = {"magistrado": "Fulano"}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = pop_deprecated_alias(kwargs, "magistrado", "relator")
        assert result == "Fulano"
        assert "magistrado" not in kwargs
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "magistrado" in str(w[0].message)
        assert "relator" in str(w[0].message)


# --- resolve_deprecated_alias ---

class TestResolveDeprecatedAlias:

    def test_alias_absent_returns_current(self):
        kwargs: dict = {}
        result = resolve_deprecated_alias(kwargs, "magistrado", "relator", "Beltrana")
        assert result == "Beltrana"

    def test_alias_absent_with_none_current(self):
        kwargs: dict = {}
        result = resolve_deprecated_alias(kwargs, "magistrado", "relator", None)
        assert result is None

    def test_alias_present_canonical_unset_returns_alias(self):
        kwargs = {"magistrado": "Fulano"}
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = resolve_deprecated_alias(kwargs, "magistrado", "relator", None)
        assert result == "Fulano"
        assert "magistrado" not in kwargs
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)

    def test_collision_raises(self):
        kwargs = {"magistrado": "Fulano"}
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="relator.*magistrado"):
                resolve_deprecated_alias(kwargs, "magistrado", "relator", "Beltrana")

    def test_custom_sentinel_empty_string(self):
        """Para clients que usam ``str = ""`` como default (TJPB/TJRN/TJRO)."""
        kwargs = {"nr_processo": "0000000-00.2024.8.15.0001"}
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolve_deprecated_alias(
                kwargs, "nr_processo", "numero_processo", "", sentinel=""
            )
        assert result == "0000000-00.2024.8.15.0001"

    def test_custom_sentinel_collision(self):
        kwargs = {"nr_processo": "A"}
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            with pytest.raises(ValueError, match="numero_processo.*nr_processo"):
                resolve_deprecated_alias(
                    kwargs, "nr_processo", "numero_processo", "B", sentinel=""
                )

    def test_custom_sentinel_empty_current_not_collision(self):
        """``current_value=""`` com sentinel=="" nao colide — trata como nao setado."""
        kwargs = {"nr_processo": "X"}
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = resolve_deprecated_alias(
                kwargs, "nr_processo", "numero_processo", "", sentinel=""
            )
        assert result == "X"
