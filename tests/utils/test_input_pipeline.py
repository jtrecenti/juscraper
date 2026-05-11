"""Unit tests for the canonical input-validation pipeline (cjsg/cjpg)."""
from __future__ import annotations

from datetime import date, datetime
from typing import ClassVar

import pytest
from pydantic import ConfigDict, ValidationError

from juscraper.schemas.cjsg import SearchBase
from juscraper.schemas.mixins import DataJulgamentoMixin, DataPublicacaoMixin
from juscraper.utils.params import apply_input_pipeline_search, raise_on_extra_kwargs, validate_intervalo_datas


class _SchemaSimples(SearchBase):
    """Schema minimo para testar o pipeline (sem filtros de data)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    relator: str = ""


class _SchemaComJulgamento(SearchBase, DataJulgamentoMixin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class _SchemaComAmbas(SearchBase, DataJulgamentoMixin, DataPublicacaoMixin):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class _SchemaIsoBackend(SearchBase, DataJulgamentoMixin):
    """Schema com BACKEND_DATE_FORMAT ISO (igual aos tribunais 1C-a)."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)
    BACKEND_DATE_FORMAT: ClassVar[str] = "%Y-%m-%d"


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
            max_dias=366, origem_mensagem="O eSAJ",
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
    """Schema sem mixin de data deve rejeitar kwargs de data como extra_forbidden.

    Auto-fill (refs bug TJSP cjpg) é gated por ``schema_cls.model_fields`` —
    schemas sem ``DataJulgamentoMixin`` não disparam fill nem warning, deixam
    o ``extra_forbidden`` virar ``TypeError`` direto.
    """
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


def test_apply_input_pipeline_single_bound_data_autopreenche_fim():
    """Só ``_inicio`` passado: pipeline preenche ``_fim=hoje`` (refs bug TJSP cjpg).

    Antes o single-bound era no-op em ``validate_intervalo_datas`` e o
    backend recebia ``dtFim=`` vazio, levando o paginador a iterar sobre
    dezenas de milhares de páginas. Agora o auto-fill no pipeline preenche
    ``_fim`` com a data atual e emite ``UserWarning``.
    """
    hoje = date.today().strftime("%d/%m/%Y")
    kwargs = {"data_julgamento_inicio": "01/01/2024"}
    with pytest.warns(UserWarning, match=r"data_julgamento_fim"):
        inp = apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
            # max_dias=None para o teste não esbarrar na janela de 366d
            # (auto-fill preenche com hoje, e a janela 2024→hoje pode passar de 366d)
        )
    assert inp.data_julgamento_inicio == "01/01/2024"
    assert inp.data_julgamento_fim == hoje


def test_apply_input_pipeline_single_bound_data_fim_autopreenche_inicio():
    """Só ``_fim`` passado: pipeline preenche ``_inicio="01/01/1990"``."""
    kwargs = {"data_julgamento_fim": "31/12/2024"}
    with pytest.warns(UserWarning, match=r"01/01/1990"):
        inp = apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1, kwargs=kwargs,
        )
    assert inp.data_julgamento_inicio == "01/01/1990"
    assert inp.data_julgamento_fim == "31/12/2024"


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
            max_dias=30, origem_mensagem="O TJRN",
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


# --- Cobertura de BACKEND_DATE_FORMAT (1C-a) -------------------------------


def test_apply_input_pipeline_backend_iso_accepts_iso_date():
    """Schema com BACKEND_DATE_FORMAT ISO aceita ``YYYY-MM-DD``."""
    kwargs = {
        "data_julgamento_inicio": "2024-01-01",
        "data_julgamento_fim": "2024-03-31",
    }
    inp = apply_input_pipeline_search(
        _SchemaIsoBackend, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs=kwargs,
    )
    assert inp.data_julgamento_inicio == "2024-01-01"
    assert inp.data_julgamento_fim == "2024-03-31"


def test_apply_input_pipeline_default_br_coerces_iso_date():
    """Schema sem BACKEND_DATE_FORMAT (default ``%d/%m/%Y``) aceita ISO via coerção (refs #173)."""
    kwargs = {
        "data_julgamento_inicio": "2024-01-01",   # ISO -> coage p/ BR
        "data_julgamento_fim": "2024-12-31",
    }
    inp = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs=kwargs,
    )
    assert inp.data_julgamento_inicio == "01/01/2024"
    assert inp.data_julgamento_fim == "31/12/2024"


def test_apply_input_pipeline_backend_iso_coerces_br_date():
    """Schema com BACKEND_DATE_FORMAT ISO aceita ``DD/MM/YYYY`` via coerção (refs #173)."""
    kwargs = {
        "data_julgamento_inicio": "01/01/2024",   # BR -> coage p/ ISO
        "data_julgamento_fim": "31/03/2024",
    }
    inp = apply_input_pipeline_search(
        _SchemaIsoBackend, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs=kwargs,
    )
    assert inp.data_julgamento_inicio == "2024-01-01"
    assert inp.data_julgamento_fim == "2024-03-31"


# --- Cobertura de coerção tolerante de formatos de data (refs #173) ---------


@pytest.mark.parametrize("entrada,esperado", [
    ("01/03/2024", "01/03/2024"),    # BR canonical
    ("01-03-2024", "01/03/2024"),    # BR com hífen
    ("2024-03-01", "01/03/2024"),    # ISO
    ("2024/03/01", "01/03/2024"),    # ISO com barra
])
def test_apply_input_pipeline_br_backend_aceita_quatro_strings(entrada, esperado):
    """Backend BR (default ``%d/%m/%Y``) aceita as 4 variações de string."""
    inp = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1,
        kwargs={"data_julgamento_inicio": entrada, "data_julgamento_fim": entrada},
    )
    assert inp.data_julgamento_inicio == esperado
    assert inp.data_julgamento_fim == esperado


@pytest.mark.parametrize("entrada,esperado", [
    ("01/03/2024", "2024-03-01"),
    ("01-03-2024", "2024-03-01"),
    ("2024-03-01", "2024-03-01"),
    ("2024/03/01", "2024-03-01"),
])
def test_apply_input_pipeline_iso_backend_aceita_quatro_strings(entrada, esperado):
    """Backend ISO (``%Y-%m-%d``) aceita as 4 variações de string."""
    inp = apply_input_pipeline_search(
        _SchemaIsoBackend, "Test.cjsg()",
        pesquisa="x", paginas=1,
        kwargs={"data_julgamento_inicio": entrada, "data_julgamento_fim": entrada},
    )
    assert inp.data_julgamento_inicio == esperado
    assert inp.data_julgamento_fim == esperado


def test_apply_input_pipeline_aceita_datetime_date():
    """``datetime.date`` é coercido para o BACKEND_DATE_FORMAT do schema."""
    inp_br = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1,
        kwargs={
            "data_julgamento_inicio": date(2024, 1, 15),
            "data_julgamento_fim": date(2024, 3, 31),
        },
    )
    assert inp_br.data_julgamento_inicio == "15/01/2024"
    assert inp_br.data_julgamento_fim == "31/03/2024"

    inp_iso = apply_input_pipeline_search(
        _SchemaIsoBackend, "Test.cjsg()",
        pesquisa="x", paginas=1,
        kwargs={
            "data_julgamento_inicio": date(2024, 1, 15),
            "data_julgamento_fim": date(2024, 3, 31),
        },
    )
    assert inp_iso.data_julgamento_inicio == "2024-01-15"
    assert inp_iso.data_julgamento_fim == "2024-03-31"


def test_apply_input_pipeline_aceita_datetime_datetime():
    """``datetime.datetime`` é coercido tratado como ``date`` (componente time descartado)."""
    inp = apply_input_pipeline_search(
        _SchemaIsoBackend, "Test.cjsg()",
        pesquisa="x", paginas=1,
        kwargs={
            "data_julgamento_inicio": datetime(2024, 1, 15, 10, 30, 0),
            "data_julgamento_fim": datetime(2024, 3, 31, 23, 59, 59),
        },
    )
    assert inp.data_julgamento_inicio == "2024-01-15"
    assert inp.data_julgamento_fim == "2024-03-31"


def test_apply_input_pipeline_formato_irreconhecivel_levanta_value_error():
    """Formato fora dos 4 aceitos (ex.: dotted) cai no validate_intervalo_datas."""
    with pytest.raises(ValueError, match="Formato esperado"):
        apply_input_pipeline_search(
            _SchemaIsoBackend, "Test.cjsg()",
            pesquisa="x", paginas=1,
            kwargs={
                "data_julgamento_inicio": "2024.01.15",
                "data_julgamento_fim": "2024.03.31",
            },
        )


def test_apply_input_pipeline_tipo_inesperado_levanta_value_error():
    """Tipo não suportado (ex.: int) faz passthrough no coerce e o
    ``validate_intervalo_datas`` converte o ``TypeError`` cru do
    ``strptime`` na mensagem amigável de formato (refs #173)."""
    with pytest.raises(ValueError, match="Formato esperado"):
        apply_input_pipeline_search(
            _SchemaIsoBackend, "Test.cjsg()",
            pesquisa="x", paginas=1,
            kwargs={
                "data_julgamento_inicio": 20240115,
                "data_julgamento_fim": 20240331,
            },
        )


def test_validate_intervalo_datas_aceita_typeerror_do_strptime():
    """Cobertura unitária da captura de ``TypeError`` em validate_intervalo_datas."""
    with pytest.raises(ValueError, match="Formato esperado"):
        validate_intervalo_datas(20240115, 20240331, formato="%Y-%m-%d", max_dias=None)


# --- Cobertura dos parâmetros nominais de data (refs #174) -------------------


def test_apply_input_pipeline_aceita_datas_nominais():
    """Datas passadas como argumentos nominais chegam ao schema."""
    inp = apply_input_pipeline_search(
        _SchemaComAmbas, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs={},
        data_julgamento_inicio="01/01/2024",
        data_julgamento_fim="31/03/2024",
        data_publicacao_inicio="2024-02-01",
        data_publicacao_fim="2024-04-30",
    )
    assert inp.data_julgamento_inicio == "01/01/2024"
    assert inp.data_julgamento_fim == "31/03/2024"
    assert inp.data_publicacao_inicio == "01/02/2024"     # coercida para BR
    assert inp.data_publicacao_fim == "30/04/2024"


def test_apply_input_pipeline_data_nominal_e_kwargs_levanta_collision():
    """Mesma data nominal e via kwargs ao mesmo tempo é colisão (ValueError)."""
    with pytest.raises(ValueError, match="nominal e via kwargs"):
        apply_input_pipeline_search(
            _SchemaComJulgamento, "Test.cjsg()",
            pesquisa="x", paginas=1,
            kwargs={"data_julgamento_inicio": "01/01/2024"},
            data_julgamento_inicio="02/01/2024",
        )


def test_apply_input_pipeline_data_nominal_none_nao_re_injeta():
    """Data nominal com valor ``None`` não polui kwargs nem o schema."""
    inp = apply_input_pipeline_search(
        _SchemaComJulgamento, "Test.cjsg()",
        pesquisa="x", paginas=1, kwargs={},
        data_julgamento_inicio=None,
        data_julgamento_fim=None,
    )
    assert inp.data_julgamento_inicio is None
    assert inp.data_julgamento_fim is None


# --- Cobertura de consume_pesquisa_aliases / nullable_pesquisa ---------------


def test_apply_input_pipeline_consume_pesquisa_aliases_pop_query():
    """Com ``consume_pesquisa_aliases=True`` o helper resolve ``query`` em kwargs."""
    with pytest.warns(DeprecationWarning, match="'query' está deprecado"):
        inp = apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa=None, paginas=1,
            kwargs={"query": "dano moral"},
            consume_pesquisa_aliases=True,
        )
    assert inp.pesquisa == "dano moral"


def test_apply_input_pipeline_consume_pesquisa_aliases_passthrough():
    """Sem alias e com ``pesquisa`` definido, consume_pesquisa_aliases é noop."""
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="direito", paginas=1, kwargs={},
        consume_pesquisa_aliases=True,
    )
    assert inp.pesquisa == "direito"


def test_apply_input_pipeline_nullable_pesquisa_aceita_string_vazia():
    """Com ``nullable_pesquisa=True``, ``pesquisa=""`` sem alias é aceito (caso TJSP cjpg)."""
    inp = apply_input_pipeline_search(
        _SchemaSimples, "Test.cjsg()",
        pesquisa="", paginas=1, kwargs={},
        consume_pesquisa_aliases=True,
        nullable_pesquisa=True,
    )
    assert inp.pesquisa == ""


def test_apply_input_pipeline_nullable_pesquisa_resolve_alias():
    """Com ``nullable_pesquisa=True`` e alias presente, alias é consumido normalmente."""
    with pytest.warns(DeprecationWarning):
        inp = apply_input_pipeline_search(
            _SchemaSimples, "Test.cjsg()",
            pesquisa="", paginas=1,
            kwargs={"termo": "habeas corpus"},
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
        )
    assert inp.pesquisa == "habeas corpus"
