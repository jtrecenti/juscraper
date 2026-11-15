"""Offline contract tests for TJMG ``cposg`` (consulta processual 2a instancia).

Samples capturados de ``www4.tjmg.jus.br/juridico/sf`` em 26/09/2026:

* ``resultado_single`` — CNJ com um recurso (apelacao criminal).
* ``resultado_multi`` — CNJ com dois recursos (apelacao + embargos).
* ``resultado_segredo`` — todos os recursos em segredo de justica.
* ``resultado_baixado`` — processo fisico antigo (2010), sem "NUMERO TJMG".
* ``resultado_not_found`` — "Nenhum processo encontrado".
* ``partes_*`` — pagina "Todas as Partes/Advogados" de cada recurso
  (``partes_baixado`` e o recurso ``/002``; ``partes_baixado_1``, o agravo
  ``/001``, capturado em 14/11/2026 pelo script abaixo).

Recaptura: ``python -m tests.fixtures.capture.tjmg_cposg``. Os processos
evoluem no tribunal (baixa, novos recursos, anonimizacao de nomes), entao
uma recaptura pode exigir ajustar os valores esperados abaixo.
"""
from __future__ import annotations

import pandas as pd
import pytest
import requests
import responses
from responses import matchers

import juscraper as jus
from juscraper.courts.tjmg.client import TJMGScraper
from juscraper.courts.tjmg.cposg_parse import parse_partes
from juscraper.courts.tjmg.schemas import OutputCPOSGTJMG
from tests._helpers import load_sample, load_sample_bytes

BASE = "https://www4.tjmg.jus.br/juridico/sf"
RESULTADO_URL = f"{BASE}/proc_resultado2.jsp"
PARTES_URL = f"{BASE}/proc_partes_advogados2.jsp"

EXPECTED_COLUMNS = {
    "id_cnj",
    "processo",
    "processo_interno",
    "segredo_justica",
    "situacao",
    "secretaria",
    "classe",
    "assunto",
    "orgao_julgador",
    "data_cadastramento",
    "data_distribuicao",
    "partes",
}


def _add(url: str, numero: str, sample: str, status: int = 200) -> None:
    responses.add(
        responses.GET,
        url,
        body=load_sample_bytes("tjmg", f"cposg/{sample}.html"),
        status=status,
        content_type="text/html; charset=ISO-8859-1",
        match=[matchers.query_param_matcher({"listaProcessos": numero})],
    )


@pytest.fixture
def scraper():
    return jus.scraper("tjmg", sleep_time=0)


TENTATIVAS = TJMGScraper.perfis_http["cposg"].max_retries


@responses.activate
def test_cposg_single_returns_partes_and_advogados(scraper):
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert isinstance(df, pd.DataFrame)
    assert set(df.columns) >= EXPECTED_COLUMNS
    assert len(df) == 1
    row = df.iloc[0]
    assert row["id_cnj"] == "00003597920208130205"
    assert row["processo"] == "0000359-79.2020.8.13.0205"
    assert row["processo_interno"] == "1.0000.26.408376-7/001"
    assert row["classe"] == "Apelação Criminal"
    assert row["orgao_julgador"] == "3ª CÂMARA CRIMINAL"
    assert row["situacao"] == "ATIVO"
    assert not row["segredo_justica"]
    assert str(row["data_distribuicao"]) == "2026-06-09"
    assert row["partes"][0] == {
        "tipo": "Apelante",
        "nome": "LEANDRO SERGIO DIAS",
        "baixa": None,
        "advogados": [{"oab": "165085N/MG", "nome": "LUIS FERNANDO BATISTA"}],
    }
    assert [p["tipo"] for p in row["partes"]] == ["Apelante", "Apelado", "Vítima"]
    for record in df.to_dict(orient="records"):
        OutputCPOSGTJMG.model_validate(record)


@responses.activate
def test_cposg_multi_recursos_one_row_each(scraper):
    _add(RESULTADO_URL, "50003445720258130461", "resultado_multi")
    _add(PARTES_URL, "10000261492847001", "partes_multi_1")
    _add(PARTES_URL, "10000261492847002", "partes_multi_2")

    df = scraper.cposg(["5000344-57.2025.8.13.0461"])

    assert list(df["processo_interno"]) == ["1.0000.26.149284-7/001", "1.0000.26.149284-7/002"]
    assert list(df["classe"]) == ["Apelação Cível", "Embargos de Declaração-Cv"]
    apelante = df.iloc[0]["partes"][0]
    assert apelante["nome"] == "RAFAELA LUCIA MARCELINO"
    assert [a["oab"] for a in apelante["advogados"]] == ["159502N/MG", "164867N/MG", "182853N/MG"]
    assert df.iloc[1]["partes"][1]["tipo"] == "Embargado"


@responses.activate
def test_cposg_accepts_numero_tjmg(scraper):
    _add(RESULTADO_URL, "10000264083767001", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("1.0000.26.408376-7/001")

    assert df.iloc[0]["processo"] == "0000359-79.2020.8.13.0205"


@responses.activate
def test_cposg_baixado_without_numero_tjmg_header(scraper):
    _add(RESULTADO_URL, "00370502120108130439", "resultado_baixado")
    _add(PARTES_URL, "10439100037050001", "partes_baixado_1")
    _add(PARTES_URL, "10439100037050002", "partes_baixado")

    df = scraper.cposg("0037050-21.2010.8.13.0439")

    assert list(df["processo_interno"]) == ["1.0439.10.003705-0/001", "1.0439.10.003705-0/002"]
    assert list(df["situacao"]) == ["BAIXADO", "BAIXADO"]
    agravante = df.iloc[0]["partes"][0]
    assert (agravante["tipo"], agravante["nome"]) == ("Agravante", "MUNICIPIO DE MURIAE")
    assert agravante["baixa"] == "30/07/2010 - REMETIDOS à COMARCA DE ORIGEM"
    apelado = df.iloc[1]["partes"][1]
    assert apelado["baixa"] == "04/05/2012 - REMETIDOS à COMARCA DE ORIGEM"
    assert apelado["nome"] == "MUNICIPIO DE MURIAE"
    assert len(apelado["advogados"]) == 2


@responses.activate
def test_cposg_segredo_skips_partes_request(scraper):
    _add(RESULTADO_URL, "50055464220238130701", "resultado_segredo")

    df = scraper.cposg("5005546-42.2023.8.13.0701")

    assert len(df) == 4
    assert df["segredo_justica"].all()
    assert df["partes"].isna().all()
    assert len(responses.calls) == 1


@responses.activate
def test_cposg_not_found_keeps_id_cnj_row(scraper):
    _add(RESULTADO_URL, "12345678920208130024", "resultado_not_found")

    df = scraper.cposg("1234567-89.2020.8.13.0024")

    assert len(df) == 1
    assert df.iloc[0]["id_cnj"] == "12345678920208130024"


def test_cposg_rejects_unknown_kwarg(scraper):
    with pytest.raises(TypeError, match="foo"):
        scraper.cposg("0000359-79.2020.8.13.0205", foo=1)


def test_cposg_rejects_invalid_length(scraper):
    with pytest.raises(ValueError, match="17 digitos"):
        scraper.cposg("123")


@pytest.mark.parametrize(
    "falha",
    [
        pytest.param(requests.Timeout("lento"), id="timeout"),
        pytest.param(
            requests.exceptions.ChunkedEncodingError(
                ConnectionResetError(104, "Connection reset by peer")
            ),
            id="chunked-connection-reset",
        ),
        pytest.param(requests.ConnectionError("reset"), id="connection-error"),
    ],
)
@responses.activate
def test_cposg_retries_falha_de_rede(scraper, mocker, falha):
    """Timeout e conexao derrubada ganham nova tentativa (#440)."""
    mocker.patch("time.sleep")
    responses.add(responses.GET, RESULTADO_URL, body=falha)
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert df.iloc[0]["processo_interno"] == "1.0000.26.408376-7/001"


@responses.activate
def test_cposg_warns_when_retries_exhausted(scraper, mocker):
    mocker.patch("time.sleep")
    for _ in range(TENTATIVAS):
        responses.add(responses.GET, RESULTADO_URL, body=requests.Timeout("lento"))

    with pytest.warns(UserWarning, match="1 consulta"):
        df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert list(df.columns) == ["id_cnj"]


@responses.activate
def test_cposg_500_persistente_no_resultado_nao_aborta_lote(scraper, mocker):
    """``RetryExhaustedError`` (5xx esgotado) vira aviso e o lote segue para o proximo numero."""
    mocker.patch("time.sleep")
    for _ in range(TENTATIVAS):
        responses.add(
            responses.GET,
            RESULTADO_URL,
            status=500,
            match=[matchers.query_param_matcher({"listaProcessos": "12345678920208130024"})],
        )
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    with pytest.warns(UserWarning, match="12345678920208130024"):
        df = scraper.cposg(["1234567-89.2020.8.13.0024", "0000359-79.2020.8.13.0205"])

    falhas = [c for c in responses.calls if "12345678920208130024" in c.request.url]
    assert len(falhas) == TENTATIVAS
    assert list(df["id_cnj"]) == ["12345678920208130024", "00003597920208130205"]
    assert pd.isna(df.iloc[0]["processo"])
    assert df.iloc[1]["processo_interno"] == "1.0000.26.408376-7/001"


@responses.activate
def test_cposg_500_persistente_nas_partes_mantem_recurso(scraper, mocker):
    """5xx esgotado na pagina de partes deixa ``partes=None`` sem perder os dados do recurso."""
    mocker.patch("time.sleep")
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    for _ in range(TENTATIVAS):
        responses.add(responses.GET, PARTES_URL, status=500)

    with pytest.warns(UserWarning, match="10000264083767001"):
        df = scraper.cposg("0000359-79.2020.8.13.0205")

    row = df.iloc[0]
    assert row["processo_interno"] == "1.0000.26.408376-7/001"
    assert not row["segredo_justica"]
    assert row["partes"] is None


@responses.activate
def test_cposg_500_seguido_de_timeout_divide_as_mesmas_tentativas(scraper, mocker):
    """O caso observado (500 e depois leitura travada) se resolve dentro do perfil."""
    mocker.patch("time.sleep")
    responses.add(responses.GET, RESULTADO_URL, status=500)
    responses.add(responses.GET, RESULTADO_URL, body=requests.ReadTimeout("lento"))
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    _add(PARTES_URL, "10000264083767001", "partes_single")

    df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert df.iloc[0]["processo_interno"] == "1.0000.26.408376-7/001"
    assert [c.request.req_kwargs["timeout"] for c in responses.calls] == [(10, 30)] * 4


@responses.activate
def test_cposg_politica_ajusta_tentativas(mocker):
    """``politica={"cposg": ...}`` muda o numero de tentativas do cposg."""
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjmg", sleep_time=0, politica={"cposg": {"max_retries": 1}})
    responses.add(responses.GET, RESULTADO_URL, body=requests.ConnectionError("reset"))

    with pytest.warns(UserWarning, match="1 consulta"):
        scraper.cposg("0000359-79.2020.8.13.0205")

    assert len(responses.calls) == 1


@responses.activate
def test_cposg_mantem_advogado_com_oab_fora_do_padrao(scraper):
    """Advogado e identificado pela estrutura da tabela, nao pelo formato da OAB."""
    partes = load_sample_bytes("tjmg", "cposg/partes_single.html").replace(b"165085N/MG", b"12.345-A/MG")
    _add(RESULTADO_URL, "00003597920208130205", "resultado_single")
    responses.add(
        responses.GET,
        PARTES_URL,
        body=partes,
        content_type="text/html; charset=ISO-8859-1",
        match=[matchers.query_param_matcher({"listaProcessos": "10000264083767001"})],
    )

    df = scraper.cposg("0000359-79.2020.8.13.0205")

    assert df.iloc[0]["partes"][0]["advogados"] == [{"oab": "12.345-A/MG", "nome": "LUIS FERNANDO BATISTA"}]


@pytest.mark.parametrize(
    ("sample", "esperado"),
    [
        pytest.param(
            "partes_single",
            [
                {
                    "tipo": "Apelante",
                    "nome": "LEANDRO SERGIO DIAS",
                    "baixa": None,
                    "advogados": [{"oab": "165085N/MG", "nome": "LUIS FERNANDO BATISTA"}],
                },
                {"tipo": "Apelado", "nome": "MINISTÉRIO PÚBLICO - MPMG", "baixa": None, "advogados": []},
                {"tipo": "Vítima", "nome": "M.F.S.", "baixa": None, "advogados": []},
            ],
            id="single",
        ),
        pytest.param(
            "partes_multi_1",
            [
                {
                    "tipo": "Apelante",
                    "nome": "RAFAELA LUCIA MARCELINO",
                    "baixa": None,
                    "advogados": [
                        {"oab": "159502N/MG", "nome": "VICTOR SANTANA LINS CERQUEIRA"},
                        {"oab": "164867N/MG", "nome": "GABRIEL SANTOS DURAES"},
                        {"oab": "182853N/MG", "nome": "WELLINGTON VICENTE DE BARROS"},
                    ],
                },
                {
                    "tipo": "Apelado",
                    "nome": "VALE S/A",
                    "baixa": None,
                    "advogados": [{"oab": "74175N/MG", "nome": "DANILO FERNANDEZ MIRANDA"}],
                },
            ],
            id="multi-1",
        ),
        pytest.param(
            "partes_multi_2",
            [
                {
                    "tipo": "Embargante",
                    "nome": "RAFAELA LUCIA MARCELINO",
                    "baixa": None,
                    "advogados": [{"oab": "164867N/MG", "nome": "GABRIEL SANTOS DURAES"}],
                },
                {
                    "tipo": "Embargado",
                    "nome": "VALE S/A",
                    "baixa": None,
                    "advogados": [{"oab": "74175N/MG", "nome": "DANILO FERNANDEZ MIRANDA"}],
                },
            ],
            id="multi-2",
        ),
        pytest.param(
            "partes_baixado",
            [
                {
                    "tipo": "Apelante",
                    "nome": "DEFENSORIA PÚBLICA ESTADO MINAS GERAIS",
                    "baixa": "04/05/2012 - REMETIDOS à COMARCA DE ORIGEM",
                    "advogados": [{"oab": "606D/MG", "nome": "MARCUS TARCÍSIO SILVA DE CASTRO"}],
                },
                {
                    "tipo": "Apelado",
                    "nome": "MUNICIPIO DE MURIAE",
                    "baixa": "04/05/2012 - REMETIDOS à COMARCA DE ORIGEM",
                    "advogados": [
                        {"oab": "63583N/MG", "nome": "GRACE QUELE DA SILVA TOLEDO LINARES"},
                        {"oab": "79267N/MG", "nome": "FILIPE DE ALMEIDA CASTRO"},
                    ],
                },
            ],
            id="baixado",
        ),
    ],
)
def test_parse_partes_preserva_campos_dos_samples_reais(sample, esperado):
    """Os samples capturados preservam tipo, nome, baixa e advogados."""
    html = load_sample("tjmg", f"cposg/{sample}.html", encoding="iso-8859-1")

    assert parse_partes(html) == esperado


@pytest.mark.parametrize("metodo", ["cposg", "cposg_download"])
@responses.activate
def test_cposg_aviso_de_falha_aponta_para_quem_chamou(scraper, mocker, metodo):
    """O ``UserWarning`` sai atribuido ao codigo do usuario, nao ao ``client.py``."""
    mocker.patch("time.sleep")
    for _ in range(TENTATIVAS):
        responses.add(responses.GET, RESULTADO_URL, status=500)

    with pytest.warns(UserWarning) as avisos:
        getattr(scraper, metodo)("0000359-79.2020.8.13.0205")

    assert avisos[0].filename == __file__


@pytest.mark.parametrize(
    ("substituto", "esperado"),
    [
        pytest.param(
            b"<td>&nbsp;</td><td>&nbsp;</td></tr><tr><td>165085N/MG</td>",
            [{"oab": "165085N/MG", "nome": "LUIS FERNANDO BATISTA"}],
            id="linha-vazia-ignorada",
        ),
        pytest.param(
            b"<td></td>",
            [{"oab": None, "nome": "LUIS FERNANDO BATISTA"}],
            id="sem-oab-mantido",
        ),
    ],
)
def test_parse_partes_linhas_de_advogado_incompletas(substituto, esperado):
    """Linha com as duas celulas vazias nao vira advogado; OAB vazia com nome vira."""
    html = (
        load_sample_bytes("tjmg", "cposg/partes_single.html")
        .replace(b"<td>165085N/MG</td>", substituto)
        .decode("iso-8859-1")
    )

    assert parse_partes(html)[0]["advogados"] == esperado
