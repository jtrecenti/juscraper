"""Regras do schema ``InputCJSGTJGO`` que valem so para o TJGO.

As tabelas que cruzam tribunais ficam em ``tests/schemas/test_domain_rejection.py``.
"""
from __future__ import annotations

import re
from typing import get_args

import pytest
from pydantic import ValidationError

from juscraper.courts.tjgo.schemas import ORGAOS_POR_INSTANCIA_E_AREA, InputCJSGTJGO, OutputCJSGTJGO
from tests._helpers import load_sample


def test_tjgo_id_serventia_subtipo_int_vira_string():
    assert InputCJSGTJGO(pesquisa="x", id_serventia_subtipo=14).id_serventia_subtipo == "14"
    assert InputCJSGTJGO(pesquisa="x").id_serventia_subtipo == "0"


def _tipos_do_script_tjgo() -> list[tuple[str, str, str]]:
    """``(areaId, servTipoId, codigo)`` do array ``tipos`` do script do formulário do TJGO."""
    script = load_sample("tjgo", "cjsg/consulta_jurisprudencia.js", encoding="latin-1")
    tipos = script.split("const tipos", 1)[1].split("];", 1)[0]
    return re.findall(r'"areaId": "(\d+)", "servTipoId": "(\d+)", "codigo": "(\d+)"', tipos)


def test_tjgo_id_serventia_subtipo_bate_com_o_seletor_do_projudi():
    """A lista do ``Literal`` vem do array ``tipos`` do script do formulário (#207)."""
    codigos = {"0"} | {codigo for _, _, codigo in _tipos_do_script_tjgo()}
    campo = InputCJSGTJGO.model_fields["id_serventia_subtipo"].annotation
    assert set(get_args(campo)) == codigos


def test_tjgo_id_instancia_bate_com_o_seletor_do_projudi():
    """O ``Literal`` traz as opções do seletor "Instância" do formulário atual.

    ``1`` (1º grau) fica fora da comparação: deprecado, segue aceito até a 0.7.0.
    """
    html = load_sample("tjgo", "cjsg/blocked_turnstile.html", encoding="latin-1")
    select = re.search(r'<select id="Id_Instancia".*?</select>', html, re.S)
    assert select is not None
    opcoes = set(re.findall(r'<option value="(\d+)"', select.group(0)))
    aceitos = {str(v) for v in get_args(InputCJSGTJGO.model_fields["id_instancia"].annotation)}
    assert aceitos - {"1"} == opcoes


def test_tjgo_orgaos_por_instancia_e_area_batem_com_o_script_do_projudi():
    """A tabela que confere as combinacoes vem do array ``tipos`` do formulario."""
    do_script: dict[tuple[str, str], set[str]] = {}
    for area, instancia, codigo in _tipos_do_script_tjgo():
        do_script.setdefault((instancia, area), set()).add(codigo)
    assert do_script == ORGAOS_POR_INSTANCIA_E_AREA


@pytest.mark.parametrize(
    "filtros",
    [
        {"id_instancia": 151, "id_area": 1},
        {"id_instancia": "151", "id_area": "2", "id_serventia_subtipo": "6"},
        {"id_instancia": 15, "id_serventia_subtipo": 66},
        {"id_instancia": 151, "id_serventia_subtipo": 14},
        # Orgaos do 1o grau so aparecem com "Todas as instancias".
        {"id_instancia": 15, "id_serventia_subtipo": 27},
        {"id_instancia": 0, "id_area": 1, "id_serventia_subtipo": 20},
        {"id_instancia": 0, "id_area": 2, "id_serventia_subtipo": 6},
    ],
)
def test_tjgo_recusa_combinacao_que_o_formulario_nao_monta(filtros):
    with pytest.raises(ValidationError, match="formulario do Projudi"):
        InputCJSGTJGO(pesquisa="x", **filtros)


@pytest.mark.parametrize(
    "filtros",
    [
        {"id_instancia": 151, "id_serventia_subtipo": 6},
        {"id_instancia": 15, "id_area": 1, "id_serventia_subtipo": 22},
        {"id_instancia": 15, "id_area": 2, "id_serventia_subtipo": "22"},
        {"id_instancia": 0, "id_serventia_subtipo": 27},
        {"id_instancia": 0, "id_area": 2, "id_serventia_subtipo": 42},
        {"id_instancia": 0, "id_area": 1},
        # ``1`` (deprecado, fora do formulario) fica sem conferencia.
        {"id_instancia": 1, "id_area": 2, "id_serventia_subtipo": 14},
    ],
)
def test_tjgo_aceita_combinacao_que_o_formulario_monta(filtros):
    InputCJSGTJGO(pesquisa="x", **filtros)


def test_tjgo_output_accepts_parser_shape():
    """OutputCJSGTJGO aceita o shape real do parser (sem ``ementa``, com ``texto``).

    O parser do TJGO (``src/juscraper/courts/tjgo/parse.py``) entrega
    o conteudo do documento em ``texto`` e nao produz coluna ``ementa``,
    ao contrario dos demais cjsg. O schema tem que refletir isso em vez
    de herdar ``ementa: str`` required de :class:`OutputCJSGBase`.
    """
    row = {
        "processo": "0000000-00.2024.8.09.0001",
        "id_arquivo": "abc",
        "serventia": "1a Vara",
        "relator": "Fulano",
        "tipo_ato": "Decisao",
        "data_publicacao": "2024-01-15",
        "texto": "Conteudo do documento ...",
    }
    model = OutputCJSGTJGO(**row)
    assert model.processo == row["processo"]
    assert model.ementa is None
