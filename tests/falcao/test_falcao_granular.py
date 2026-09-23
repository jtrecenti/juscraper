"""Granular tests (offline) para helpers do agregador Falcao."""
import json

import pytest
import requests

from juscraper.aggregators.falcao.client import FalcaoScraper
from juscraper.aggregators.falcao.download import build_pesquisa_params, gerar_session_id, verificar_resposta
from juscraper.aggregators.falcao.parse import parse_documentos, parse_total
from juscraper.core.exceptions import BotChallengeBlockedError
from tests._helpers import load_sample


def _sample(colecao: str) -> dict:
    return json.loads(load_sample("falcao", f"pesquisa/{colecao}_normal.json"))


def _documento(colecao: str, **campos) -> dict:
    return parse_documentos({"documentos": [campos]}, colecao)[0]


def _resposta(status: int, corpo: bytes = b"", **headers) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = corpo
    resp.headers.update(headers)
    resp.url = "https://jurisprudencia.jt.jus.br/x"
    return resp


def test_gerar_session_id_formato():
    sid = gerar_session_id()
    assert sid.startswith("_")
    assert len(sid) == 8
    assert sid[1:].isalnum()


def test_build_params_pagina_1based_para_0based():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1
    )
    assert p["page"] == 0
    p3 = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=3
    )
    assert p3["page"] == 2


def test_build_params_lista_vira_csv():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1,
        relator=["A", "B"], tribunais="TST",
    )
    assert p["nomeRelator"] == "A,B"
    assert p["tribunais"] == "TST"


def test_build_params_omite_filtros_none():
    p = build_pesquisa_params(
        pesquisa="x", colecao="acordaos", session_id="_a", pagina=1
    )
    assert "nomeRelator" not in p
    assert "dataInicio" not in p
    assert "temEmenta" not in p


def test_parse_total_le_quantidade():
    body = _sample("acordaos")
    assert parse_total(body) == body["quantidadeTotal"]


def test_parse_total_sem_chave_levanta():
    with pytest.raises(ValueError):
        parse_total({"documentos": []})


def test_parse_documentos_renomeia_processo_e_datas():
    docs = parse_documentos(_sample("acordaos"), "acordaos")
    d = docs[0]
    assert "numeroProcesso" not in d  # renomeado
    assert d["processo"]
    assert "dataJulgamento" not in d and "data_julgamento" in d
    assert "dataJuntada" not in d and "data_juntada" in d
    assert d["colecao"] == "acordaos"


@pytest.mark.parametrize(
    "campos,esperado",
    [
        ({"tribunal": "TST", "tipo": "SUMULA", "numero": "392", "id": 1}, "TST-SUM-392"),
        (
            {"tribunal": "TST", "tipo": "ORIENTACAO_JURISPRUDENCIAL", "numero": "130", "id": 2,
             "orgaoJulgador": "Subseção II Especializada em Dissídios Individuais"},
            "TST-OJ-SBDI2-130",
        ),
        (
            {"tribunal": "TST", "tipo": "ORIENTACAO_JURISPRUDENCIAL", "numero": "130", "id": 3,
             "orgaoJulgador": "Subseção I Especializada em Dissídios Individuais"},
            "TST-OJ-SBDI1-130",
        ),
        # OJ de orgao fora do mapa: o id garante a unicidade.
        (
            {"tribunal": "TRT2", "tipo": "ORIENTACAO_JURISPRUDENCIAL", "numero": "5", "id": 77,
             "orgaoJulgador": "Seção Especializada em Dissídios Individuais 1"},
            "TRT2-OJ-5-id77",
        ),
        # Tipo fora do mapa entra com o valor bruto.
        ({"tribunal": "TRT4", "tipo": "TESE_JURIDICA_PREVALECENTE", "numero": "3", "id": 4},
         "TRT4-TESE_JURIDICA_PREVALECENTE-3"),
        # Sem numero (caso observado em precedentes do TRT9): cai para o id.
        ({"tribunal": "TRT9", "tipo": "SUMULA", "numero": None, "id": 915}, "TRT9-id915"),
        ({"tribunal": "TRT9", "numero": "12", "id": 916}, "TRT9-id916"),
    ],
)
def test_processo_de_precedente_e_chave_composta(campos, esperado):
    assert _documento("precedentes", **campos)["processo"] == esperado


def test_processo_de_precedente_desambigua_sumula_e_oj_de_mesmo_numero():
    sumula = _documento("precedentes", tribunal="TST", tipo="SUMULA", numero="392", id=1)
    oj = _documento(
        "precedentes", tribunal="TST", tipo="ORIENTACAO_JURISPRUDENCIAL", numero="392", id=2,
        orgaoJulgador="Subseção I Especializada em Dissídios Individuais",
    )
    assert sumula["processo"] != oj["processo"]


def test_precedentes_do_sample_tem_processo_unico():
    docs = parse_documentos(_sample("precedentes"), "precedentes")
    processos = [d["processo"] for d in docs]
    assert all(processos)
    assert len(set(processos)) == len(processos)


def test_relator_cai_para_nomeredator_quando_nomerelator_vazio():
    d = _documento("sentencas", nomeRelator="", nomeRedator="FULANA DE TAL")
    assert d["relator"] == "FULANA DE TAL"


def test_relator_prefere_nomerelator_quando_preenchido():
    d = _documento("recursorevista", nomeRelator="RELATOR", nomeRedator="REDATOR")
    assert d["relator"] == "RELATOR"


def test_relator_de_acordaos_preservado():
    d = _documento("acordaos", relator="DESEMBARGADOR X")
    assert d["relator"] == "DESEMBARGADOR X"


@pytest.mark.parametrize("colecao", ["sentencas", "decisoesmonocraticas"])
def test_relator_preenchido_nos_samples_de_juiz_singular(colecao):
    docs = parse_documentos(_sample(colecao), colecao)
    assert all(d["relator"] for d in docs)


@pytest.mark.parametrize(
    "colecao,campos,classe,sigla",
    [
        ("acordaos", {"classeProcesso": "Recurso Ordinário Trabalhista", "siglaClasseProcesso": "ROT"},
         "Recurso Ordinário Trabalhista", "ROT"),
        ("decisoesmonocraticas", {"classeProcesso": "Agravo de Petição", "siglaClasseProcesso": "AP"},
         "Agravo de Petição", "AP"),
        ("sentencas", {"classeProcessual": "ATOrd",
                       "classeProcessualPorExtenso": "AÇÃO TRABALHISTA - RITO ORDINÁRIO"},
         "AÇÃO TRABALHISTA - RITO ORDINÁRIO", "ATOrd"),
        # Sem o par por extenso, 'classeProcessual' nao e tratado como sigla.
        ("recursorevista", {"classeProcessual": "Recurso de Revista"}, "Recurso de Revista", None),
        ("precedentes", {}, None, None),
    ],
)
def test_classe_e_classe_sigla(colecao, campos, classe, sigla):
    d = _documento(colecao, **campos)
    assert d["classe"] == classe
    assert d["classe_sigla"] == sigla


@pytest.mark.parametrize("colecao", ["acordaos", "sentencas", "decisoesmonocraticas", "recursorevista"])
def test_classe_sigla_preenchida_nos_samples(colecao):
    docs = parse_documentos(_sample(colecao), colecao)
    assert all(d["classe_sigla"] for d in docs)


def test_ementa_vira_texto_sem_html():
    d = _documento(
        "acordaos",
        ementa='<p style="x"><strong>DANO MORAL.</strong> Caracteriza&ccedil;&atilde;o\n  do  dano.</p>',
    )
    assert d["ementa"] == "DANO MORAL. Caracterização do dano."


@pytest.mark.parametrize("ementa", ["", "   ", "<p> </p>", None])
def test_ementa_vazia_vira_none(ementa):
    assert _documento("acordaos", ementa=ementa)["ementa"] is None


def test_ementa_do_sample_sem_tags():
    docs = parse_documentos(_sample("acordaos"), "acordaos")
    ementas = [d["ementa"] for d in docs if d["ementa"]]
    assert ementas
    assert not any("<" in e and ">" in e for e in ementas)


@pytest.mark.parametrize("colecao", ["acordaos", "sentencas", "precedentes"])
def test_campos_highlight_nao_entram_na_saida(colecao):
    body = _sample(colecao)
    assert any(k.startswith("highlight") for doc in body["documentos"] for k in doc)
    docs = parse_documentos(body, colecao)
    assert not any(k.startswith("highlight") for d in docs for k in d)


@pytest.mark.parametrize(
    "total,tamanho,esperado",
    [(0, 10, 1), (5, 10, 1), (10, 10, 1), (11, 10, 2), (95, 10, 10),
     (999999, 10, 1000), (999999, 5, 2000)],
)
def test_total_paginas_respeita_teto(total, tamanho, esperado):
    # teto do backend = 10000 resultados
    assert FalcaoScraper._total_paginas(total, tamanho) == esperado


@pytest.mark.parametrize(
    "paginas,total_pags,esperado",
    [
        (None, 3, [1, 2, 3]),
        (range(1, 10), 3, [1, 2, 3]),
        (range(2, 5), 10, [2, 3, 4]),
        (range(1, 10, 2), 6, [1, 3, 5]),
        (range(2, 20, 3), 100, [2, 5, 8, 11, 14, 17]),
        ([1, 5, 99], 4, [1]),
    ],
)
def test_resolver_paginas(paginas, total_pags, esperado):
    assert list(FalcaoScraper._resolver_paginas(paginas, total_pags)) == esperado


def test_verificar_resposta_waf_cloudfront_vira_bot_challenge():
    resp = _resposta(403, b"<HTML><TITLE>ERROR: The request could not be satisfied</TITLE></HTML>",
                     **{"Server": "CloudFront", "Content-Type": "text/html"})
    with pytest.raises(BotChallengeBlockedError, match="CloudFront"):
        verificar_resposta(resp)


def test_verificar_resposta_403_json_vira_valueerror():
    resp = _resposta(403, '{"userMessage":"Tentativa inválida de acesso ao sistema"}'.encode(),
                     **{"Content-Type": "application/json"})
    with pytest.raises(ValueError, match="Tentativa inválida de acesso"):
        verificar_resposta(resp)


def test_verificar_resposta_429_longo_vira_httperror():
    resp = _resposta(429, b'{"userMessage":"Too Many Requests"}',
                     **{"Content-Type": "application/json", "x-rate-limit-retry-after-seconds": "20880"})
    with pytest.raises(requests.HTTPError, match="5h48min"):
        verificar_resposta(resp)


@pytest.mark.parametrize(
    "status,headers",
    [
        (200, {}),
        (429, {"x-rate-limit-retry-after-seconds": "30"}),
        (429, {}),
        (403, {"Server": "Apache", "Content-Type": "text/html"}),
        (500, {"Server": "CloudFront"}),
    ],
)
def test_verificar_resposta_deixa_passar_o_resto(status, headers):
    verificar_resposta(_resposta(status, **headers))
