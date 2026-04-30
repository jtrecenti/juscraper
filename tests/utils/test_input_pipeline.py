"""Unit tests for the canonical input-validation pipeline (cjsg/cjpg)."""
from __future__ import annotations

import pytest
from pydantic import ConfigDict, ValidationError

from juscraper.schemas.cjsg import SearchBase
from juscraper.schemas.mixins import DataJulgamentoMixin, DataPublicacaoMixin
from juscraper.utils.params import apply_input_pipeline_search, raise_on_extra_kwargs


class _SchemaSimples(SearchBase):
    """Schema minimo para testar o pipeline (sem filtros de data)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    relator: str = ""


class _SchemaComJulgamento(SearchBase, DataJulgamentoMixin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class _SchemaComAmbas(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


def test_apply_input_pipeline_returns_validated_model():
    inp = apply_input_pipeline_search(
        _SchemaSimples,
        "Test.cjsg()",
        pesquisa="dano moral",
        paginas=2,
        kwargs={},
        relator="FULANO",
    )

    assert inp.pesquisa == "dano moral"
    assert inp.paginas == range(1, 3)
    assert inp.relator == "FULANO"


def test_apply_input_pipeline_int_paginas_normalized_to_range():
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="x", paginas=5, kwargs={},
    )
    assert inp.paginas == range(1, 6)


def test_apply_input_pipeline_unknown_kwarg_raises_typeerror():
    kwargs = {"kwarg_inventado": "x"}
    with pytest.raises(TypeError, match=r"Test\.cjsg\(\) got unexpected keyword argument\(s\): 'kwarg_inventado'"):
        apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )


def test_apply_input_pipeline_multiple_unknown_kwargs_listed():
    kwargs = {"foo": "1", "bar": "2"}
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\)"):
        apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )


def test_apply_input_pipeline_data_inicio_alias_emits_deprecation_warning():
    kwargs = {"data_inicio": "01/01/2024", "data_fim": "31/03/2024"}
    with pytest.warns(DeprecationWarning) as wlist:
        inp = apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )

    assert inp.data_julgamento_inicio == "01/01/2024"
    assert inp.data_julgamento_fim == "31/03/2024"
    messages = [str(w.message) for w in wlist]
    assert any("data_inicio" in m for m in messages)
    assert any("data_fim" in m for m in messages)


def test_apply_input_pipeline_de_ate_alias_maps_to_canonical():
    kwargs = {"data_publicacao_de": "01/01/2024", "data_publicacao_ate": "31/01/2024"}
    with pytest.warns(DeprecationWarning):
        inp = apply_input_pipeline_search(
            _SchemaComAmbas, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )
    assert inp.data_publicacao_inicio == "01/01/2024"
    assert inp.data_publicacao_fim == "31/01/2024"


def test_apply_input_pipeline_invalid_date_interval_raises_valueerror_when_max_dias_set():
    kwargs = {
        "data_julgamento_inicio": "01/01/2024",
        "data_julgamento_fim": "01/01/2026",  # > 366 dias
    }
    with pytest.raises(ValueError, match=r"aceita no máximo"):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
            max_dias=366, origem="O eSAJ",
        )


def test_apply_input_pipeline_inicio_after_fim_raises_valueerror():
    kwargs = {
        "data_julgamento_inicio": "31/12/2024",
        "data_julgamento_fim": "01/01/2024",
    }
    with pytest.raises(ValueError, match=r"posterior"):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )


def test_apply_input_pipeline_data_filter_on_schema_without_mixin_raises_typeerror():
    """Schema sem mixin de data deve rejeitar kwargs de data como extra_forbidden."""
    kwargs = {"data_julgamento_inicio": "01/01/2024"}
    with pytest.raises(TypeError, match=r"got unexpected keyword argument\(s\): 'data_julgamento_inicio'"):
        apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )


def test_apply_input_pipeline_kwargs_dict_is_consumed_in_place():
    kwargs = {"data_inicio": "01/01/2024", "data_fim": "31/01/2024"}
    with pytest.warns(DeprecationWarning):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )
    # pop_normalize_aliases mutates the caller's kwargs dict
    assert "data_inicio" not in kwargs
    assert "data_fim" not in kwargs
    assert "data_julgamento_inicio" not in kwargs


def test_raise_on_extra_kwargs_passes_through_when_other_errors_present():
    """Quando o mix de erros nao e puro extra_forbidden, o helper nao deve
    levantar TypeError — espera-se que o caller relevante o erro original."""

    class _S(SearchBase):
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    try:
        # Dispara extra_forbidden AND missing-required (pesquisa)
        _S(extra="x")
    except ValidationError as exc:
        # erro misto -> nao deve levantar
        raise_on_extra_kwargs(exc, "Test")
    else:
        pytest.fail("Schema should have raised ValidationError")


def test_raise_on_extra_kwargs_raises_typeerror_for_pure_extra_forbidden():
    class _S(SearchBase):
        model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    try:
        _S(pesquisa="x", extra="y")
    except ValidationError as exc:
        with pytest.raises(TypeError, match=r"got unexpected keyword argument"):
            raise_on_extra_kwargs(exc, "Test")
    else:
        pytest.fail("Schema should have raised ValidationError")


# --- Cobertura adicional pos-review do PR #135 ---------------------------


def test_apply_input_pipeline_pesquisa_vazia_aceita():
    """TJSP cjpg aceita pesquisa='' — o helper nao deve interferir."""
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjpg()",
        pesquisa="", paginas=1, kwargs={},
    )
    assert inp.pesquisa == ""


def test_apply_input_pipeline_paginas_range_passthrough():
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="x", paginas=range(1, 4), kwargs={},
    )
    assert inp.paginas == range(1, 4)


def test_apply_input_pipeline_paginas_list_passthrough():
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="x", paginas=[1, 3, 5], kwargs={},
    )
    assert inp.paginas == [1, 3, 5]


def test_apply_input_pipeline_paginas_none_passthrough():
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="x", paginas=None, kwargs={},
    )
    assert inp.paginas is None


def test_apply_input_pipeline_single_bound_data_aceita():
    """Single-bound (so inicio, fim=None) e no-op em validate_intervalo_datas."""
    kwargs = {"data_julgamento_inicio": "01/01/2024"}
    inp = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs=kwargs,
        max_dias=366, origem="O eSAJ",
    )
    assert inp.data_julgamento_inicio == "01/01/2024"
    assert inp.data_julgamento_fim is None


def test_apply_input_pipeline_max_dias_none_aceita_janela_grande():
    """max_dias=None (default) aceita janelas arbitrarias mas ainda valida ordem."""
    kwargs = {
        "data_julgamento_inicio": "01/01/2020",
        "data_julgamento_fim": "31/12/2024",  # ~5 anos
    }
    inp = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs=kwargs,
    )
    assert inp.data_julgamento_inicio == "01/01/2020"
    assert inp.data_julgamento_fim == "31/12/2024"


def test_apply_input_pipeline_max_dias_none_ainda_rejeita_inicio_apos_fim():
    """Mesmo sem teto, inicio > fim continua erro."""
    kwargs = {
        "data_julgamento_inicio": "31/12/2024",
        "data_julgamento_fim": "01/01/2024",
    }
    with pytest.raises(ValueError, match=r"posterior"):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )


def test_apply_input_pipeline_origem_custom_aparece_na_mensagem():
    """origem propaga para a mensagem de erro quando max_dias e excedido."""
    kwargs = {
        "data_julgamento_inicio": "01/01/2024",
        "data_julgamento_fim": "01/03/2024",  # 60 dias
    }
    with pytest.raises(ValueError, match=r"O TJRN aceita no máximo 30 dias"):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
            max_dias=30, origem="O TJRN",
        )


def test_apply_input_pipeline_canonical_x_kwargs_collision_raises_typeerror():
    """Colisao entre canonical_filters e kwargs vira TypeError do Python (sem
    merge silencioso). Caller precisa popar conflitos antes de invocar o helper."""
    with pytest.raises(TypeError, match=r"got multiple values for keyword argument 'relator'"):
        apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa="x", paginas=1,
            kwargs={"relator": "FROM_KWARGS"},
            relator="FROM_CANONICAL",
        )
