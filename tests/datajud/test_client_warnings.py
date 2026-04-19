"""Avisos visíveis e validação de input no DataJud (refs #57)."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import juscraper as jus


@pytest.fixture()
def datajud():
    return jus.scraper("datajud", verbose=0)


class TestRaisesValueError:
    def test_invalid_tribunal_raises(self, datajud):
        with pytest.raises(ValueError, match="não encontrado nos mappings"):
            datajud.listar_processos(tribunal="XPTO_INEXISTENTE")

    def test_missing_required_params_raises(self, datajud):
        with pytest.raises(ValueError, match="tribunal.*numero_processo"):
            datajud.listar_processos()


class TestEmitsWarnings:
    def test_invalid_cnj_emits_warning(self, datajud):
        # CNJ com poucos dígitos depois da limpeza
        with pytest.warns(UserWarning, match="CNJ inválido"):
            datajud.listar_processos(numero_processo="123")

    def test_unmapped_tribunal_cnj_emits_warning(self, datajud):
        # CNJ com 20 dígitos válidos mas par (id_justica, id_tribunal) sem
        # mapeamento. Aqui id_justica=9 (Militar Estadual), tribunal=99 (n/a).
        # Layout CNJ: NNNNNNN DD AAAA J TT OOOO = 7+2+4+1+2+4 = 20.
        cnj = "12345678920249990001"
        assert len(cnj) == 20
        with pytest.warns(UserWarning, match="tribunal não mapeado"):
            datajud.listar_processos(numero_processo=cnj)

    def test_no_valid_cnj_emits_warning_and_returns_empty(self, datajud):
        with pytest.warns(UserWarning):
            df = datajud.listar_processos(numero_processo="123")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestApiFailureEmitsWarning:
    def test_http_error_emits_warning(self, datajud):
        # Forca call_datajud_api a retornar None simulando uma falha HTTP
        with patch(
            "juscraper.aggregators.datajud.client.call_datajud_api",
            return_value=None,
        ), pytest.warns(UserWarning, match="falha ao consultar"):
            df = datajud.listar_processos(tribunal="TJSP")
        assert df.empty
