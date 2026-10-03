"""Integração ao vivo do ``cpopg`` do TJPE.

Marcado ``integration`` e fora do default; rode com ``pytest -m integration``.
O AWS WAF do TJPE desafia de forma intermitente: sem o Playwright instalado
(extra ``juscraper[waf]``), o teste passa enquanto o WAF deixa a sessão
passar e levanta ``ImportError`` quando desafia. Desafio repetido depois da
renovação do cookie vira ``WafChallengeError``, que o marker ``anti_bot``
converte em xfail.
"""
from __future__ import annotations

import pandas as pd
import pytest

import juscraper as jus

pytestmark = pytest.mark.anti_bot

# Execução cível pública da capital, com documentos visíveis sem login.
_PUBLICO_CNJ = "00963022520218172001"


@pytest.mark.integration
def test_cpopg_traz_processo_publico_com_documentos(tmp_path) -> None:
    scraper = jus.scraper("tjpe")
    df = scraper.cpopg(_PUBLICO_CNJ, download_pecas=True, diretorio=str(tmp_path))
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["processo"] == "0096302-25.2021.8.17.2001"
    assert row["classe"]
    assert isinstance(row["documentos"], list) and row["documentos"]
    assert row["pecas"], "nenhuma peça pública baixada"
