"""Polos do TRF6 ``cpopg`` pela posição na tabela de partes, qualquer que seja o rótulo."""
from __future__ import annotations

import warnings

import pytest
import responses

import juscraper as jus
from juscraper.courts.trf6 import download
from juscraper.courts.trf6.parse import parse_detail
from tests._helpers import load_sample_bytes

GET_URL = "https://eproc1g.trf6.jus.br/eproc/externo_controlador.php"


def _detalhe(sample: str) -> str:
    return load_sample_bytes("trf6", f"cpopg/{sample}").decode("latin-1")


@pytest.mark.parametrize(
    ("sample", "passivo"),
    [
        # Procedimento comum: AUTOR | RÉU.
        ("detail_normal.html", "SUBPROCURADORIA REGIONAL FEDERAL DA 6 REGIÃO"),
        # O mesmo processo, já em cumprimento de sentença: EXEQUENTE | EXECUTADO.
        ("detail_cumprimento_sentenca.html", "NPREV - ATUAÇÃO PREVIDENCIÁRIA PRIORITÁRIA"),
    ],
)
def test_polos_pela_posicao(sample, passivo, recwarn):
    record = parse_detail(_detalhe(sample))

    assert [p["descricao"] for p in record["polo_ativo"]] == [
        "- SANDRA MARCIA TOSTES (017.**********) | ALESSANDRA APARECIDA ESTEVAO SOARES MG142599"
    ]
    (polo_passivo,) = record["polo_passivo"]
    assert polo_passivo["descricao"].startswith("- INSTITUTO NACIONAL DO SEGURO SOCIAL")
    assert passivo in polo_passivo["descricao"]
    assert record["mpf"]
    assert record["perito"]
    assert not recwarn.list


def _sem_faixa_dupla(rotulo: str) -> str:
    """O sample real com a faixa dos polos trocada por uma de um só rótulo, como a do MPF."""
    return _detalhe("detail_cumprimento_sentenca.html").replace(
        '<th class="infraTh" width="50%">EXEQUENTE</th><th class="infraTh" width="50%">EXECUTADO</th>',
        f'<th class="infraTh" colspan="2">{rotulo}</th>',
    )


def test_sem_faixa_dupla_vale_o_rotulo_autor():
    record = parse_detail(_sem_faixa_dupla("AUTOR"))
    assert [p["descricao"].split(" (")[0] for p in record["polo_ativo"]] == ["- SANDRA MARCIA TOSTES"]
    assert record["polo_passivo"] == []


def test_faixa_dupla_de_mpf_e_perito_nao_e_a_dos_polos():
    html = _detalhe("detail_normal.html").replace(
        '<th class="infraTh" width="50%">AUTOR</th><th class="infraTh" width="50%">RÉU</th>',
        '<th class="infraTh" width="50%">MPF</th><th class="infraTh" width="50%">PERITO</th>',
    )
    record = parse_detail(html)
    assert record["polo_ativo"] == []
    assert record["polo_passivo"] == []


@responses.activate
def test_cpopg_sem_polos_avisa_uma_vez(monkeypatch):
    """Sem a faixa dos polos nem AUTOR/RÉU: polos vazios, a linha fica, e um aviso agregado sai ao fim."""
    for _ in range(2):
        responses.add(responses.GET, GET_URL, body=load_sample_bytes("trf6", "cpopg/form_initial.html"))
        responses.add(responses.POST, GET_URL, body=_sem_faixa_dupla("EXEQUENTE").encode("latin-1"))
    monkeypatch.setattr(download, "solve_captcha", lambda _b64: "abc1")

    scraper = jus.scraper("trf6", sleep_time=0)
    with warnings.catch_warnings(record=True) as avisos:
        warnings.simplefilter("always")
        df = scraper.cpopg(["10052295520234063801", "10052295520234063801"])

    assert [str(a.message) for a in avisos] == [
        "TRF6Scraper.cpopg: 2 processo(s) sem polo ativo nem passivo (10052295520234063801, 10052295520234063801). "
        "A tabela de partes não traz a faixa dos polos nem os rótulos AUTOR/RÉU; polo_ativo e polo_passivo "
        "saem vazios."
    ]
    assert list(df["processo"]) == ["1005229-55.2023.4.06.3801"] * 2
    assert list(df["motivo_falha"]) == [None, None]
