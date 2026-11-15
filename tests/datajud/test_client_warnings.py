"""Avisos visíveis e validação de input no DataJud (refs #57)."""
import pandas as pd
import pytest
import requests

import juscraper as jus
from juscraper.aggregators.datajud.parse import parse_datajud_api_response
from juscraper.core.exceptions import ColetaParcialError


@pytest.fixture()
def datajud():
    return jus.scraper("datajud", verbose=0)


class TestRaisesValueError:
    def test_invalid_tribunal_raises(self, datajud):
        with pytest.raises(ValueError, match="não encontrado nos mappings"):
            datajud.listar_processos(tribunal="XPTO_INEXISTENTE")

    def test_missing_required_params_raises(self, datajud):
        with pytest.raises(ValueError, match=r"tribunal.*numero_processo"):
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


class TestApiFailureRaisesPartialError:
    def test_http_error_lanca_erro_parcial(self, datajud, mocker):
        causa = requests.ConnectionError("falha simulada")
        mocker.patch(
            "juscraper.aggregators.datajud.client.call_datajud_api",
            side_effect=causa,
        )
        with pytest.raises(ColetaParcialError, match="falha ao consultar") as exc_info:
            datajud.listar_processos(tribunal="TJSP")

        assert exc_info.value.resultado.empty
        assert len(exc_info.value.falhas) == 1
        assert exc_info.value.falhas[0][2] is causa
        assert exc_info.value.__cause__ is causa


class TestParseErrorEmitsWarning:
    def test_malformed_hits_lanca_excecao_de_parse(self):
        # hits deveria ser lista de dicts; passando string, o .get() sobre cada
        # "hit" propaga AttributeError no parser.
        malformed = {"hits": {"hits": ["not-a-dict"]}}
        with pytest.raises(AttributeError, match="has no attribute 'get'"):
            parse_datajud_api_response(malformed)
