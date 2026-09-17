"""Validação local sem preencher limites de datas que o STF aceita abertos."""

from pydantic import ValidationError

from juscraper.utils.params import (
    coerce_brazilian_date,
    normalize_datas,
    normalize_paginas,
    normalize_pesquisa,
    pop_normalize_aliases,
    raise_on_extra_kwargs,
    validate_intervalo_datas,
)


def search_input(schema, method, pesquisa, paginas, kwargs):
    """Normaliza aliases sem completar os limites de data ausentes."""
    pesquisa = normalize_pesquisa(pesquisa, **kwargs)
    dates = normalize_datas(**kwargs)
    pop_normalize_aliases(kwargs, include_canonical=True)
    dates = {key: coerce_brazilian_date(value, schema.BACKEND_DATE_FORMAT) for key, value in dates.items()}
    for axis in ("julgamento", "publicacao"):
        inicio = dates[f"data_{axis}_inicio"]
        fim = dates[f"data_{axis}_fim"]
        # Validar o extremo isolado não deve preencher o limite ausente no payload.
        validate_intervalo_datas(
            inicio if inicio is not None else fim,
            fim if fim is not None else inicio,
            max_dias=None,
            rotulo=f"data_{axis}",
            formato=schema.BACKEND_DATE_FORMAT,
        )
    try:
        return schema(
            pesquisa=pesquisa,
            paginas=normalize_paginas(paginas),
            **{key: value for key, value in dates.items() if value is not None},
            **kwargs,
        )
    except ValidationError as exc:
        raise_on_extra_kwargs(exc, method, schema_cls=schema)
        raise
