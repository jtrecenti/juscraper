"""Testes granulares para ``juscraper.courts.tjmg.download``.

Cobrem os helpers privados do modulo (``_build_params``,
``_extract_total``, ``_fetch_page``, ``_solve_captcha``) isoladamente.
A intencao e detectar drift de assinatura/comportamento mesmo sem
promove-los a publicos: testes podem importar privados com ``_`` e o
projeto ja segue esse padrao (ver ``tests/jusbr/test_download_granular.py``
e ``tests/trf1/test_cpopg_contract.py``).

O caminho feliz de ``_solve_captcha`` (PNG -> decrypt -> DWR) ja e
exercido em ``test_cjsg_contract.py``; aqui cobrimos so o caso de borda
do lazy import (``txtcaptcha`` ausente -> ``RuntimeError`` descritivo),
conforme pedido explicito da issue #159.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest
import requests
import responses

from juscraper.courts.tjmg.download import SEARCH_URL, _build_params, _extract_total, _fetch_page, _solve_captcha
from tests._helpers import query_param_subset_matcher


def _build_params_defaults(**overrides):
    """Argumentos padrao para ``_build_params``; cada teste sobrescreve o que importa."""
    kwargs = dict(
        pesquisa="termo",
        pagina=1,
        total=1,
        pesquisar_por="ementa",
        order_by="2",
        data_julgamento_inicial="",
        data_julgamento_final="",
        data_publicacao_inicial="",
        data_publicacao_final="",
        linhas_por_pagina=10,
    )
    kwargs.update(overrides)
    return _build_params(**kwargs)


# ---------------------------------------------------------------------------
# _build_params
# ---------------------------------------------------------------------------


class TestBuildParams:
    """``_build_params`` e funcao pura; testamos cada propagacao isoladamente."""

    def test_offset_pagina_1_linhas_10(self):
        params = _build_params_defaults(pagina=1, linhas_por_pagina=10)
        assert params["numeroRegistro"] == "1"

    def test_offset_pagina_2_linhas_10(self):
        params = _build_params_defaults(pagina=2, linhas_por_pagina=10)
        assert params["numeroRegistro"] == "11"

    def test_offset_pagina_3_linhas_50(self):
        params = _build_params_defaults(pagina=3, linhas_por_pagina=50)
        assert params["numeroRegistro"] == "101"

    def test_pesquisa_propaga_para_palavras(self):
        params = _build_params_defaults(pesquisa="dano moral")
        assert params["palavras"] == "dano moral"

    def test_pesquisar_por_propaga(self):
        params = _build_params_defaults(pesquisar_por="acordao")
        assert params["pesquisarPor"] == "acordao"

    def test_order_by_propaga(self):
        params = _build_params_defaults(order_by="0")
        assert params["orderByData"] == "0"

    def test_total_e_pagina_propagam(self):
        params = _build_params_defaults(total=42, pagina=3)
        assert params["totalLinhas"] == "42"
        assert params["paginaNumero"] == "3"

    def test_datas_julgamento_propagam(self):
        params = _build_params_defaults(
            data_julgamento_inicial="01/01/2025",
            data_julgamento_final="31/01/2025",
        )
        assert params["dataJulgamentoInicial"] == "01/01/2025"
        assert params["dataJulgamentoFinal"] == "31/01/2025"

    def test_datas_publicacao_propagam(self):
        params = _build_params_defaults(
            data_publicacao_inicial="01/02/2025",
            data_publicacao_final="28/02/2025",
        )
        assert params["dataPublicacaoInicial"] == "01/02/2025"
        assert params["dataPublicacaoFinal"] == "28/02/2025"

    def test_datas_vazias_viram_strings_vazias(self):
        # Backend TJMG nao aceita ausencia das chaves; precisa "" literal.
        params = _build_params_defaults()
        for key in (
            "dataJulgamentoInicial",
            "dataJulgamentoFinal",
            "dataPublicacaoInicial",
            "dataPublicacaoFinal",
        ):
            assert params[key] == ""

    def test_linhas_por_pagina_propaga(self):
        params = _build_params_defaults(linhas_por_pagina=20)
        assert params["linhasPorPagina"] == "20"

    def test_chaves_estaticas_presentes(self):
        # Backend reclama se o form vier "limpo"; estes campos sao
        # decorativos mas obrigatorios na pratica. Guard contra remocao.
        params = _build_params_defaults()
        assert params["pesquisaPalavras"] == "Pesquisar"
        assert "Clique na lupa" in params["referenciaLegislativa"]


# ---------------------------------------------------------------------------
# _extract_total
# ---------------------------------------------------------------------------


class TestExtractTotal:
    """``_extract_total`` casca os dois padroes em ordem fixa.

    Cascata: ``muitos resultados (N)`` primeiro, ``totalLinhas=N`` depois.
    Em ``cjsg_download`` o caller curto-circuita antes quando "muitos
    resultados" aparece, mas o contrato do helper isolado contempla ambos
    os ramos.
    """

    def test_total_linhas_pattern(self):
        assert _extract_total("<html>totalLinhas=42</html>") == 42

    def test_total_linhas_em_url(self):
        html = '<a href="search?numeroRegistro=1&totalLinhas=123&x=1">'
        assert _extract_total(html) == 123

    def test_muitos_resultados_com_ponto(self):
        # ``.replace(".", "")`` em ``_extract_total`` trata separador de milhar.
        html = "Sua pesquisa retornou muitos resultados (1.234)."
        assert _extract_total(html) == 1234

    def test_muitos_resultados_com_virgula(self):
        # ``.replace(",", "")`` cobre locale alternativo; guard contra
        # remocao acidental do segundo replace em ``_extract_total``.
        html = "muitos resultados (2,500)."
        assert _extract_total(html) == 2500

    def test_muitos_resultados_simples(self):
        html = "Sua pesquisa retornou muitos resultados (50)."
        assert _extract_total(html) == 50

    def test_muitos_resultados_precede_total_linhas(self):
        # Cascata: muitos_re primeiro. Caso patologico que documenta a ordem.
        html = "muitos resultados (5) ... totalLinhas=99"
        assert _extract_total(html) == 5

    def test_returns_none_when_no_pattern(self):
        assert _extract_total("<html><body>nada aqui</body></html>") is None


# ---------------------------------------------------------------------------
# _fetch_page
# ---------------------------------------------------------------------------


def _session_request_fn(session: requests.Session):
    """``RequestFn`` minimo que delega ao ``session.request`` (mockavel por ``responses``).

    Em uso real o ``request_fn`` e ``TJMGScraper._request_with_retry``, que
    centraliza retry + ``raise_for_status``. ``_fetch_page`` depende so do
    contrato ``(method, url, **kw) -> Response`` — esse wrapper o satisfaz
    sem amarrar o teste ao stack de retry.
    """
    def request_fn(method, url, **kwargs):
        return session.request(method, url, **kwargs)
    return request_fn


class TestFetchPage:
    """``_fetch_page`` chama ``request_fn("GET", SEARCH_URL, ...)`` e forca encoding latin-1."""

    @responses.activate
    def test_get_em_search_url_com_params(self):
        responses.add(
            responses.GET,
            SEARCH_URL,
            body=b"<html>ok</html>",
            status=200,
            content_type="text/html; charset=ISO-8859-1",
            match=[query_param_subset_matcher({
                "numeroRegistro": "1",
                "palavras": "dano moral",
            })],
        )
        request_fn = _session_request_fn(requests.Session())
        result = _fetch_page(
            request_fn,
            {"numeroRegistro": "1", "palavras": "dano moral"},
        )
        assert result == "<html>ok</html>"
        assert len(responses.calls) == 1

    @responses.activate
    def test_force_encoding_iso_8859_1(self):
        # Body em latin-1; servidor anuncia utf-8 (mentira proposital).
        # ``_fetch_page`` sobrescreve ``resp.encoding`` para iso-8859-1,
        # entao o texto sai certo apesar do header errado.
        body = "AÇÃO".encode("iso-8859-1")
        responses.add(
            responses.GET,
            SEARCH_URL,
            body=body,
            status=200,
            content_type="text/html; charset=utf-8",
        )
        request_fn = _session_request_fn(requests.Session())
        result = _fetch_page(request_fn, {"palavras": "x"})
        assert result == "AÇÃO"

    def test_invoca_request_fn_com_get_e_search_url(self):
        # Contrato minimo: GET + url + params + timeout=120 (pinado para
        # detectar mudanca silenciosa do default que afetaria conexoes lentas).
        response = MagicMock()
        response.text = "<html>ok</html>"
        request_fn = MagicMock(return_value=response)

        result = _fetch_page(request_fn, {"palavras": "x"})

        assert result == "<html>ok</html>"
        request_fn.assert_called_once()
        method, url = request_fn.call_args.args
        assert method == "GET"
        assert url == SEARCH_URL
        assert request_fn.call_args.kwargs["params"] == {"palavras": "x"}
        assert request_fn.call_args.kwargs["timeout"] == 120


# ---------------------------------------------------------------------------
# _solve_captcha
# ---------------------------------------------------------------------------


class TestSolveCaptcha:
    """Caso de borda do lazy import: ``txtcaptcha`` ausente.

    O caminho feliz ja e coberto pelos contratos de ``cjsg`` em
    ``test_cjsg_contract.py``, que mockam ``sys.modules["txtcaptcha"]``
    via fixture ``mock_txtcaptcha``. Duplicar aqui exigiria reconstruir
    ``OrderedRegistry`` com os 3 GETs de PNG + 1 POST DWR; e redundante.
    """

    def test_raises_runtime_error_quando_txtcaptcha_ausente(self, mocker):
        # ``sys.modules["txtcaptcha"] = None`` faz ``import txtcaptcha``
        # levantar ``ImportError`` em Python 3 (sentinela documentada).
        mocker.patch.dict(sys.modules, {"txtcaptcha": None})
        request_fn = MagicMock()
        session = MagicMock(spec=requests.Session)
        with pytest.raises(RuntimeError, match="TJMG requires txtcaptcha"):
            _solve_captcha(request_fn, session)
        # O import e a primeira coisa: nenhum request foi disparado.
        request_fn.assert_not_called()
