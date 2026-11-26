"""Caracterização do parser de resultados TJES, compartilhado por CJSG e CJPG."""

import copy
import datetime
import json

import pandas as pd
import pytest

from juscraper.core.base import _texto_ausente_como_none
from juscraper.courts.tjes.parse import cjsg_parse

# Páginas mínimas com as bordas do parser que as respostas reais gravadas não
# reproduzem: campo canônico e campo desconhecido na entrada, listas e escalares
# misturados, data inválida, página sem ``docs``, documento vazio e processo
# repetido. Não é resposta do portal; por isso fica aqui e não em ``samples/``.
PAGINAS_COM_BORDAS = """\
[
  {
    "docs": [
      {
        "nr_processo": "0000001-00.2026.8.08.0000",
        "processo": "campo canônico ignorado na entrada",
        "ementa": "<p>Texto preservado</p>",
        "magistrado": ["Relatora A", "Relator B"],
        "relator": "ignorado",
        "orgao_julgador": "Câmara Cível",
        "classe_judicial": "Apelação",
        "classe_judicial_sigla": "AC",
        "assunto_principal": ["Dano moral"],
        "jurisdicao": null,
        "competencia": [],
        "dt_juntada": "2026-04-17T20:29:22.764Z",
        "id": "doc-1",
        "acordao": false,
        "lista_assunto": ["Consumidor", 42, null],
        "localizacao": "Gabinete",
        "cargo_julgador": ["Desembargador"],
        "cd_assunto_principal": 0,
        "cd_classe_judicial": 198,
        "id_assunto_principal": [1, 2],
        "id_classe_judicial": 198,
        "id_jurisdicao": [],
        "id_localizacao": null,
        "id_cargo_julgador": 3,
        "id_bin": 4,
        "campo_desconhecido": "descartar"
      },
      {
        "nr_processo": "0000002-00.2026.8.08.0000",
        "dt_juntada": "data inválida",
        "lista_assunto": [],
        "localizacao": {"codigo": 7},
        "competencia": ""
      }
    ]
  },
  {},
  {"docs": []},
  {"docs": [{}, {"nr_processo": "0000001-00.2026.8.08.0000", "dt_juntada": null}]}
]
"""


def test_parse_preserva_valores_colunas_ordem_e_entrada():
    paginas = json.loads(PAGINAS_COM_BORDAS)
    original = copy.deepcopy(paginas)

    # O parser devolve o que o pandas da vez produzir; o metodo publico passa a
    # saida por ``_texto_ausente_como_none``, que mantem texto ausente como
    # None tambem no pandas 3. O teste confere o valor que o usuario recebe.
    resultado = _texto_ausente_como_none(cjsg_parse(paginas))

    primeira_linha = {
        "processo": "0000001-00.2026.8.08.0000",
        "ementa": "<p>Texto preservado</p>",
        "relator": "Relatora A; Relator B",
        "orgao_julgador": "Câmara Cível",
        "classe": "Apelação",
        "classe_judicial_sigla": "AC",
        "assunto": "Dano moral",
        "jurisdicao": None,
        "competencia": None,
        "dt_juntada": datetime.date(2026, 4, 17),
        "id": "doc-1",
        "acordao": False,
        "lista_assunto": "Consumidor; 42; None",
        "localizacao": "Gabinete",
        "cargo_julgador": "Desembargador",
        "cd_assunto_principal": 0.0,
        "cd_classe_judicial": 198.0,
        "id_assunto_principal": "1; 2",
        "id_classe_judicial": 198.0,
        "id_jurisdicao": None,
        "id_localizacao": None,
        "id_cargo_julgador": 3.0,
        "id_bin": 4.0,
    }
    assert resultado.columns.tolist() == list(primeira_linha)
    assert resultado.iloc[0].to_dict() == primeira_linha
    assert resultado.index.tolist() == [0, 1, 2, 3]
    assert resultado["processo"].tolist() == [
        "0000001-00.2026.8.08.0000", "0000002-00.2026.8.08.0000", None, "0000001-00.2026.8.08.0000",
    ]
    assert resultado.loc[1, "localizacao"] == {"codigo": 7}
    assert resultado.loc[1, "competencia"] == ""
    assert resultado.loc[1, "lista_assunto"] is None
    assert resultado.loc[1:, "dt_juntada"].isna().all()
    assert resultado.loc[2].isna().all()
    assert resultado["dt_juntada"].dtype == object
    assert paginas == original


@pytest.mark.parametrize("paginas", [[], [{}], [{"docs": []}], [{}, {"docs": []}]])
def test_parse_sem_documentos_retorna_dataframe_sem_colunas(paginas):
    pd.testing.assert_frame_equal(cjsg_parse(paginas), pd.DataFrame())


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, None), ([], None), ([""], ""), ([False, 0], "False; 0"), ([[1, 2]], "[1, 2]"), (False, False)],
)
def test_parse_normaliza_listas_sem_descartar_escalares(valor, esperado):
    resultado = cjsg_parse([{"docs": [{"ementa": valor}]}])
    assert resultado.loc[0, "ementa"] == esperado
