"""Contrato do limite de 120 caracteres de ``pesquisa`` no TJSP pela API publica.

O backend eSAJ do TJSP recusa buscas acima de 120 caracteres. ``cjsg`` e
``cjpg`` levantam ``QueryTooLongError`` antes da primeira requisicao, e o
contrato vale igual nos tres caminhos de execucao:

* janela curta (download direto);
* janela longa (> 366 dias), em que o auto-chunk divide a busca em
  janelas. Antes da correcao, o erro nascia dentro do download de cada
  janela, ``run_chunked_search`` o engolia como falha de janela e o
  usuario recebia um DataFrame vazio com ``UserWarning``;
* ``count_only=True``, que desvia para o probe de contagem.

Vale tambem para os aliases deprecados ``query``/``termo``. O HTTP fica
mockado com ``responses``: no caso invalido, nenhuma requisicao pode sair;
no limite (120), a busca precisa chegar ao backend com o termo inteiro.
"""
import re
import warnings
from contextlib import nullcontext
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest
import responses

import juscraper as jus
from juscraper.courts.tjsp.exceptions import QueryTooLongError
from tests._helpers import load_sample_bytes

BASE = "https://esaj.tjsp.jus.br"

JANELAS = {
    "curta": {"data_julgamento_inicio": "01/01/2024", "data_julgamento_fim": "31/03/2024"},
    "longa": {"data_julgamento_inicio": "01/01/2022", "data_julgamento_fim": "31/12/2024"},
}


def _chamar(scraper, endpoint: str, forma: str, termo_busca: str, janela: str, count_only: bool):
    """Chama ``cjsg``/``cjpg`` passando a busca pelo nome canonico ou por alias."""
    kwargs: dict[str, str | bool] = dict(JANELAS[janela])
    if count_only:
        kwargs["count_only"] = True
    kwargs[forma] = termo_busca
    return getattr(scraper, endpoint)(**kwargs)


def _aviso_de_alias(forma: str):
    if forma == "pesquisa":
        return nullcontext()
    return pytest.warns(DeprecationWarning, match=f"'{forma}' está deprecado")


@pytest.mark.parametrize("count_only", [False, True], ids=["busca", "count_only"])
@pytest.mark.parametrize("forma", ["pesquisa", "query", "termo"])
@pytest.mark.parametrize("janela", ["curta", "longa"])
@pytest.mark.parametrize("endpoint", ["cjsg", "cjpg"])
def test_pesquisa_acima_do_limite_levanta_sem_requisicao(tmp_path, endpoint, janela, forma, count_only):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock_http:
        with _aviso_de_alias(forma), pytest.raises(
            QueryTooLongError, match=rf"do {endpoint.upper()} do TJSP.*recebido: 121 caracteres"
        ):
            _chamar(scraper, endpoint, forma, "a" * 121, janela, count_only)
        assert len(mock_http.calls) == 0


def _registrar_backend_sem_resultados(mock_http: responses.RequestsMock) -> None:
    """Responde qualquer chamada de cjsg/cjpg com a pagina de zero resultados."""
    mock_http.add(
        responses.POST,
        re.compile(rf"{re.escape(BASE)}/cjsg/resultadoCompleta\.do.*"),
        body=load_sample_bytes("tjsp", "cjsg/post_initial.html"),
        status=200,
        content_type="text/html; charset=latin-1",
    )
    mock_http.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE)}/cjsg/trocaDePagina\.do.*"),
        body=load_sample_bytes("tjsp", "cjsg/no_results.html"),
        status=200,
        content_type="text/html; charset=latin-1",
    )
    mock_http.add(
        responses.GET,
        re.compile(rf"{re.escape(BASE)}/cjpg/pesquisar\.do.*"),
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
    )


def _termos_enviados(mock_http: responses.RequestsMock) -> list[str]:
    """Extrai o termo livre de cada requisicao que carrega a busca."""
    enviados = []
    for chamada in mock_http.calls:
        requisicao = chamada.request
        if requisicao.method == "POST":
            corpo = parse_qs(requisicao.body if isinstance(requisicao.body, str) else requisicao.body.decode())
            enviados.extend(corpo.get("dados.buscaInteiroTeor", []))
        elif "/cjpg/pesquisar.do" in requisicao.url:
            enviados.extend(parse_qs(urlparse(requisicao.url).query).get("dadosConsulta.pesquisaLivre", []))
    return enviados


@pytest.mark.parametrize("count_only", [False, True], ids=["busca", "count_only"])
@pytest.mark.parametrize("forma", ["pesquisa", "query"])
@pytest.mark.parametrize("janela", ["curta", "longa"])
@pytest.mark.parametrize("endpoint", ["cjsg", "cjpg"])
def test_pesquisa_no_limite_chega_ao_backend(tmp_path, mocker, endpoint, janela, forma, count_only):
    mocker.patch("time.sleep")
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    termo_busca = "a" * 120
    n_janelas = 3 if janela == "longa" else 1

    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock_http:
        _registrar_backend_sem_resultados(mock_http)
        with _aviso_de_alias(forma), warnings.catch_warnings():
            # Uma janela que falhasse viraria ``UserWarning`` e resultado
            # vazio; como erro, a falha aparece no teste em vez de se
            # esconder atras do DataFrame vazio.
            warnings.filterwarnings("error", message="auto_chunk")
            resultado = _chamar(scraper, endpoint, forma, termo_busca, janela, count_only)

        assert _termos_enviados(mock_http) == [termo_busca] * n_janelas

    if count_only:
        assert resultado == 0
    else:
        assert isinstance(resultado, pd.DataFrame)
        assert resultado.empty
