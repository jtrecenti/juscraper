"""Caracterização dos campos opcionais da página de resultados CJPG."""
import pandas as pd
import pytest

from juscraper.courts.tjsp.cjpg_parse import cjpg_parse_single
from tests._helpers import load_sample


def test_campos_opcionais_ordem_e_normalizacao(tmp_path):
    """Mantém linhas incompletas, ordem dos campos e o último span da decisão."""
    caminho = tmp_path / "resultados.html"
    caminho.write_text(load_sample("tjsp", "cjpg/results_optional_fields.html"), encoding="utf-8")

    resultado = cjpg_parse_single(caminho)

    esperado = pd.DataFrame([
        {
            "cd_processo": "CODIGO",
            "id_processo": "1000000-00.2024.8.26.0001",
            "classe": "Classe: complemento",
            "data_disponibilizacao": "01/02/2024",
            "tipode_ato": "Sentença",
            "decisao": "Decisão completa final.",
        },
        {"cd_processo": None, "id_processo": None, "decisao": ""},
        {},
    ])
    pd.testing.assert_frame_equal(resultado, esperado)


@pytest.mark.parametrize("html", ["<html></html>", '<div id="divDadosResultado"></div>'])
def test_ausencia_de_resultados(tmp_path, html):
    caminho = tmp_path / "vazio.html"
    caminho.write_text(html, encoding="utf-8")
    pd.testing.assert_frame_equal(cjpg_parse_single(caminho), pd.DataFrame())


def test_rotulo_sem_separador_continua_rejeitado(tmp_path):
    caminho = tmp_path / "invalido.html"
    caminho.write_text(
        '<div id="divDadosResultado"><tr class="fundocinza1"><table>'
        '<tr class="fonte"><td><strong>Classe sem separador</strong></td></tr>'
        '</table></tr></div>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not enough values to unpack"):
        cjpg_parse_single(caminho)
