"""Avisos visíveis e validação de input no DataJud (refs #57)."""
import pandas as pd
import pytest

import juscraper as jus
from juscraper.aggregators.datajud.parse import parse_datajud_api_response


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
        with pytest.warns(UserWarning, match="CNJ inválido"):
            df = datajud.listar_processos(numero_processo="123")
        assert isinstance(df, pd.DataFrame)
        assert df.empty


class TestApiFailureEmitsWarning:
    def test_http_error_emits_warning(self, datajud, mocker):
        # Forca call_datajud_api a retornar None simulando uma falha HTTP
        mocker.patch(
            "juscraper.aggregators.datajud.client.call_datajud_api",
            return_value=None,
        )
        with pytest.warns(UserWarning, match="falha ao consultar"):
            df = datajud.listar_processos(tribunal="TJSP")
        assert df.empty


class TestParseErrorEmitsWarning:
    def test_malformed_hits_emits_warning(self):
        # hits deveria ser lista de dicts; passando string, o .get() sobre cada
        # "hit" levanta AttributeError e dispara o handler de exceção do parse.
        malformed = {"hits": {"hits": ["not-a-dict"]}}
        with pytest.warns(UserWarning, match="erro ao parsear"):
            df = parse_datajud_api_response(malformed)
        assert isinstance(df, pd.DataFrame)
        assert df.empty
