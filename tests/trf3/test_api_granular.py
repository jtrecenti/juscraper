"""Testes granulares do parser e da paginação do TRF3 (API JSON)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from juscraper.courts.trf3 import download
from juscraper.courts.trf3.download import RECURSOS_PAGINADOS, baixar_recurso_paginado, token_valido
from juscraper.courts.trf3.parse import parse_processo
from tests.trf3._api import SAMPLES, carregar, id_processo_do_cenario

_COLUNA_DO_RECURSO = {
    "poloAtivo": "polo_ativo",
    "poloPassivo": "polo_passivo",
    "outrosInteressados": "outros_interessados",
    "movimentacoes": "movimentacoes",
    "documentos": "documentos",
}


def _bruto(cenario: str = "paginado") -> dict[str, Any]:
    bruto: dict[str, Any] = {
        "busca": carregar("cpopg", f"{cenario}_busca.json")["result"][0],
        "dados": carregar("cpopg", f"{cenario}_dados.json"),
    }
    for recurso in RECURSOS_PAGINADOS:
        arquivos = sorted((SAMPLES / "cpopg").glob(f"{cenario}_{recurso}_page_*.json"))
        bruto[recurso] = [json.loads(a.read_text(encoding="utf-8")) for a in arquivos]
    return bruto


@pytest.mark.parametrize("recurso", RECURSOS_PAGINADOS)
def test_recurso_que_falhou_sai_none_e_nao_lista_vazia(recurso: str) -> None:
    """``None`` no bruto (erro HTTP) vira ``None``; ``[]`` significaria "o processo não tem itens"."""
    bruto = _bruto()
    bruto[recurso] = None
    registro = parse_processo(bruto)
    assert registro[_COLUNA_DO_RECURSO[recurso]] is None
    outros = [c for r, c in _COLUNA_DO_RECURSO.items() if r != recurso]
    assert all(isinstance(registro[c], list) for c in outros)


def test_recurso_sem_itens_sai_lista_vazia() -> None:
    """Página com ``result`` vazio vira lista vazia, não ``None``."""
    bruto = _bruto()
    bruto["documentos"] = [{"status": "ok", "result": [], "pageInfo": {"current": 1, "last": 0}}]
    assert parse_processo(bruto)["documentos"] == []


def test_paginacao_espera_sleep_time_entre_paginas(mocker) -> None:
    """Entre uma página e a seguinte do mesmo recurso, ``baixar_recurso_paginado`` espera ``sleep_time``."""
    paginas = [carregar("cpopg", f"paginado_movimentacoes_page_{n}.json") for n in range(5)]
    assert paginas[0]["pageInfo"]["last"] == 5
    respostas = iter(paginas)

    class _Resp:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data

        def json(self) -> dict[str, Any]:
            return self._data

    pedidas: list[int] = []

    def request_fn(method, url, *, params=None, **kwargs):
        pedidas.append(params["page"])
        return _Resp(next(respostas))

    sleep = mocker.patch.object(download.time, "sleep")
    id_processo = id_processo_do_cenario("cpopg", "paginado")
    resultado = baixar_recurso_paginado(
        request_fn, download.BASE_URL_1G, id_processo, "movimentacoes", sleep_time=0.7
    )

    assert pedidas == [0, 1, 2, 3, 4]
    assert len(resultado) == 5
    assert sleep.call_args_list == [mocker.call(0.7)] * 4


def test_token_valido_aceita_os_tokens_dos_samples() -> None:
    """Todo ``idProcesso`` e ``id`` de documento capturado passa na validação."""
    tokens = [
        item[chave]
        for arquivo in SAMPLES.glob("*/*.json")
        for chave in ("idProcesso", "id")
        for item in (json.loads(arquivo.read_text(encoding="utf-8")).get("result") or [])
        if isinstance(item, dict) and chave in item and ("_busca" in arquivo.name or "_documentos_" in arquivo.name)
    ]
    assert len(tokens) > 20
    assert all(token_valido(t) for t in tokens)


@pytest.mark.parametrize("valor", ["", "../x", "/x", "a.b", "a/b", "a b", "abc\n", "a=", None, 123])
def test_token_valido_recusa_o_que_nao_e_base64_de_url(valor: object) -> None:
    assert not token_valido(valor)
