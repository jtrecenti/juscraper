"""Testes granulares dos helpers compartilhados da família ``_trf``.

A família serve TRF1, TRF5 e TJPE (PJe ConsultaPública em JSF). Os samples
em ``tests/_trf/samples/cpopg/`` são páginas de detalhe reais do PJe JSF,
capturadas do TRF3 antes de ele migrar para a API JSON. São as únicas com
dois sliders Richfaces (movimentações e documentos) na mesma página, o que
permite testar que cada extrator pega o seu.
"""
from __future__ import annotations

import re

import pytest

from juscraper.core.exceptions import BotChallengeBlockedError
from juscraper.courts._trf.download import (
    _check_bot_challenge,
    _extract_docs_rows,
    extract_docs_pagination,
    extract_documento_urls,
    extract_movs_pagination,
    merge_docs_pages,
    merge_movs_pages,
)
from tests._helpers import load_sample_bytes


def _detail(nome: str) -> str:
    return load_sample_bytes("_trf", f"cpopg/{nome}").decode("latin-1")


class _FakeResp:
    def __init__(self, status_code: int, content: bytes, url: str = "https://example.com/x") -> None:
        self.status_code = status_code
        self.content = content
        self.url = url


def test_akamai_block_raises_dedicated_exception() -> None:
    """403 ``Access Denied`` (Akamai) vira ``BotChallengeBlockedError`` com a referência."""
    resp = _FakeResp(
        403,
        b"<HTML><HEAD><TITLE>Access Denied</TITLE></HEAD><BODY><H1>Access Denied</H1>"
        b" Reference&#32;&#35;18&#46;27f62917&#46;1779623119&#46;a59b1f4c</BODY></HTML>",
    )
    with pytest.raises(BotChallengeBlockedError) as exc_info:
        _check_bot_challenge(resp, "TRF1")  # type: ignore[arg-type]
    err = exc_info.value
    assert err.tribunal == "TRF1"
    assert err.reference == "18.27f62917.1779623119.a59b1f4c"
    msg = str(err)
    assert "aguarde" in msg
    assert "VPN" in msg or "hotspot" in msg


def test_check_bot_challenge_ignores_legitimate_403() -> None:
    """403 sem ``Access Denied`` segue para ``raise_for_status``."""
    _check_bot_challenge(_FakeResp(403, b"<html>403 - not authorized</html>"))  # type: ignore[arg-type]


def test_check_bot_challenge_ignores_non_403() -> None:
    """Só 403 dispara a detecção."""
    _check_bot_challenge(_FakeResp(500, b"Access Denied"))  # type: ignore[arg-type]


def test_extract_movs_pagination_picks_movs_slider_not_documentos() -> None:
    """Com dois sliders na página, o extrator de movimentações pega o das movimentações."""
    info = extract_movs_pagination(_detail("detail_paginated.html"))
    assert info is not None
    assert info.max_pages > 1
    assert info.container_id != info.form_id
    assert info.slider_input_name.startswith(info.form_id + ":")
    assert info.ajax_source_name.startswith(info.form_id + ":")
    assert info.view_state


def test_merge_movs_pages_noop_when_extras_empty() -> None:
    """Sem páginas extras, o HTML volta idêntico."""
    detail = _detail("detail_paginated.html")
    assert merge_movs_pages(detail, []) is detail


def test_extract_docs_pagination_detects_its_own_slider() -> None:
    """Mais de 15 documentos expõem um slider próprio, distinto do das movimentações."""
    detail = _detail("detail_paginated.html")
    movs_info = extract_movs_pagination(detail)
    docs_info = extract_docs_pagination(detail)
    assert movs_info is not None and docs_info is not None
    assert docs_info.max_pages > 1
    assert movs_info.form_id != docs_info.form_id
    assert movs_info.slider_input_name != docs_info.slider_input_name


def test_extract_docs_pagination_returns_none_when_no_slider() -> None:
    """Até 15 documentos, o PJe não renderiza o slider."""
    assert extract_docs_pagination(_detail("detail_normal.html")) is None


def test_merge_docs_pages_splices_into_docs_tbody() -> None:
    """``merge_docs_pages`` acrescenta as linhas no tbody dos documentos."""
    detail = _detail("detail_paginated.html")
    page1_urls = extract_documento_urls(detail)
    m = re.search(
        r'<tbody[^>]*\bid="[^"]*:processoDocumentoGridTab:tb"[^>]*>.*?</tbody>',
        detail,
        re.DOTALL,
    )
    assert m is not None
    fake_page2 = m.group()
    assert _extract_docs_rows(fake_page2)
    merged = merge_docs_pages(detail, [fake_page2])
    assert len(merged) > len(detail)
    # Os ids repetidos da página forjada são deduplicados pelo extrator.
    assert len(extract_documento_urls(merged)) == len(page1_urls)
