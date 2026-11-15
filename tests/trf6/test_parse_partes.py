"""Polos do TRF6 ``cpopg`` pela posição na tabela de partes, qualquer que seja o rótulo."""
from __future__ import annotations

import pytest

from juscraper.courts.trf6.parse import parse_detail
from tests._helpers import load_sample_bytes


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


def test_tabela_sem_par_de_polos_avisa():
    """Sem a faixa de dois rótulos, os polos saem vazios com aviso, e não em silêncio."""
    html = _detalhe("detail_cumprimento_sentenca.html").replace(
        '<th class="infraTh" width="50%">EXEQUENTE</th><th class="infraTh" width="50%">EXECUTADO</th>',
        '<th class="infraTh" colspan="2">EXEQUENTE</th>',
    )
    with pytest.warns(UserWarning, match=r"1005229-55\.2023\.4\.06\.3801 .*rótulos: EXEQUENTE\)"):
        record = parse_detail(html)
    assert record["polo_ativo"] == []
    assert record["polo_passivo"] == []
