"""Parse das respostas do JusBR, nas formas que ``download`` deixa passar."""
import logging

from juscraper.aggregators.jusbr.parse import parse_process_details_response, parse_process_list_response

CNJ = "00000000000000000000"


def test_lista_devolve_o_content():
    processos = [{"numeroProcesso": "A"}, {"numeroProcesso": "B"}]
    assert parse_process_list_response({"content": processos}) is processos


def test_detalhes_em_objeto_solto_viram_a_linha():
    detalhes = {"numeroProcesso": "N", "idCodexTribunal": 7}

    linha = parse_process_details_response(detalhes, CNJ)

    assert linha == {"processo": CNJ, "numeroProcesso": "N", "idCodexTribunal": 7, "detalhes": detalhes}


def test_detalhes_em_lista_usam_o_primeiro_e_avisam_quando_ha_mais(caplog):
    primeiro, segundo = {"numeroProcesso": "1"}, {"numeroProcesso": "2"}

    with caplog.at_level(logging.WARNING, logger="juscraper.aggregators.jusbr.parse"):
        linha = parse_process_details_response([primeiro, segundo], CNJ)

    assert linha["detalhes"] is primeiro
    assert "lista com 2 itens para o CNJ 00000000000000000000; só o primeiro é usado" in caplog.text


def test_detalhes_em_lista_de_um_item_nao_avisam(caplog):
    with caplog.at_level(logging.WARNING, logger="juscraper.aggregators.jusbr.parse"):
        linha = parse_process_details_response([{"numeroProcesso": "1"}], CNJ)

    assert linha["numeroProcesso"] == "1"
    assert not caplog.records
