"""Shared helpers for juscraper tests.

Centralizes fixture loading and ``responses`` matchers. Used by parser tests
(direct call), contract tests (via ``responses.add(body=load_sample(...))``)
and granular tests.

Examples
--------
>>> from tests._helpers import load_sample
>>> html = load_sample("tjsp", "cjsg/results_normal_page_01.html")
"""
import json
import re
from collections.abc import Callable, Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, parse_qsl, urlparse

import pytest
import responses
import yaml
from requests import PreparedRequest
from responses import matchers

from juscraper import _SCRAPERS
from juscraper.courts._esaj.acordao import parse_cursor

_SAMPLES_ROOT = Path(__file__).parent


def classes_publicadas() -> dict[type, bool]:
    """Classes que ``docs/_quarto.yml`` manda o quartodoc documentar -> se a página traz os herdados.

    ``include_inherited`` vale como no quartodoc: o da entrada, senão o das
    ``options`` da seção, senão o das ``options`` globais.
    """
    config = yaml.safe_load((_SAMPLES_ROOT.parent / "docs" / "_quarto.yml").read_text(encoding="utf-8"))["quartodoc"]
    padrao = config.get("options", {}).get("include_inherited", False)
    classes = {}
    for secao in config["sections"]:
        da_secao = secao.get("options", {}).get("include_inherited", padrao)
        for alvo in secao["contents"]:
            entrada = alvo if isinstance(alvo, dict) else {"name": alvo}
            modulo, _, nome = f"juscraper.{entrada['name']}".rpartition(".")
            objeto = getattr(import_module(modulo), nome)
            if isinstance(objeto, type):
                classes[objeto] = bool(entrada.get("include_inherited", da_secao))
    return classes


def classe_da_sigla(sigla: str) -> type:
    """Classe do raspador que ``jus.scraper(sigla)`` instancia, pelo mapa ``_SCRAPERS``."""
    modulo, nome = _SCRAPERS[sigla].split(":")
    classe: type = getattr(import_module(modulo), nome)
    return classe


def load_sample(tribunal: str, relative_path: str, *, encoding: str = "utf-8") -> str:
    """Load a sample fixture as string.

    Parameters
    ----------
    tribunal : str
        Court directory under ``tests/`` (e.g., ``"tjsp"``, ``"tjac"``).
    relative_path : str
        Path inside ``tests/<tribunal>/samples/`` (e.g., ``"cjsg/results_normal_page_01.html"``).
    encoding : str
        File encoding. Defaults to ``"utf-8"``.

    Returns
    -------
    str
        File contents.

    Raises
    ------
    FileNotFoundError
        If the sample file does not exist.
    """
    path = _SAMPLES_ROOT / tribunal / "samples" / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Sample not found: {path}")
    return path.read_text(encoding=encoding)


def load_sample_bytes(tribunal: str, relative_path: str) -> bytes:
    """Load a sample fixture as raw bytes.

    Use when the parser needs to handle encoding itself (eSAJ HTML
    is served as latin-1, for example).
    """
    path = _SAMPLES_ROOT / tribunal / "samples" / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Sample not found: {path}")
    return path.read_bytes()


def url_enviada(request: PreparedRequest) -> str:
    """URL de uma requisição já enviada (``responses.calls[i].request``).

    O ``PreparedRequest`` tipa ``url`` como ``str | None``; depois do envio
    ela sempre existe, e o helper falha alto se não existir.
    """
    if request.url is None:
        raise AssertionError("requisição registrada sem URL")
    return request.url


def urls_enviadas() -> list[str]:
    """URLs das requisições registradas em ``responses.calls``, na ordem de envio."""
    return [url_enviada(chamada.request) for chamada in responses.calls]


def _sem_query(url: str) -> str:
    return url.split("?", 1)[0]


def rotas_enviadas() -> list[str]:
    """Último segmento do caminho de cada requisição registrada, na ordem de envio.

    ``https://esaj.tjsp.jus.br/cpopg/search.do?x=1`` vira ``"search.do"``.
    """
    return [_sem_query(url).rsplit("/", 1)[-1] for url in urls_enviadas()]


def chamadas_para(rota: str) -> list[PreparedRequest]:
    """Requisições registradas cuja URL, sem a query, termina em ``rota``.

    ``rota`` pode ser o fim do caminho (``"search.do"``) ou a URL inteira sem
    query, quando o último segmento não basta para separar os endpoints.
    """
    return [
        chamada.request
        for chamada in responses.calls
        if _sem_query(url_enviada(chamada.request)).endswith(rota)
    ]


def corpo_enviado(request: PreparedRequest) -> str:
    """Corpo de uma requisição já enviada como texto; vazio quando não há corpo."""
    body = request.body or ""
    return body.decode("utf-8") if isinstance(body, bytes) else body


def corpo_json_enviado(request: PreparedRequest) -> Any:
    """Corpo JSON de uma requisição já enviada, decodificado."""
    return json.loads(corpo_enviado(request))


def corpo_form_enviado(request: PreparedRequest) -> dict[str, str]:
    """Corpo ``application/x-www-form-urlencoded`` de uma requisição já enviada.

    Para contratos que conferem os nomes de campo do backend contra um
    dicionário literal, sem depender do builder que o raspador usa (#514).
    Campos vazios ficam no resultado.
    """
    return dict(parse_qsl(corpo_enviado(request), keep_blank_values=True))


def params_enviados(request: PreparedRequest) -> dict[str, str | list[str]]:
    """Query string de uma requisição já enviada, como o ``responses`` a registrou.

    O ``responses`` acrescenta ``params`` ao ``PreparedRequest`` em tempo de
    execução, fora dos stubs do ``requests``: chave com um valor vira ``str``,
    chave repetida em sequência vira lista, e campos vazios ficam.
    """
    return cast("dict[str, str | list[str]]", cast("Any", request).params)


def timeout_enviado(request: PreparedRequest) -> Any:
    """``timeout`` que o ``requests`` passou ao adaptador ao enviar a requisição.

    Lido de ``req_kwargs``, que o ``responses`` acrescenta ao
    ``PreparedRequest`` em tempo de execução, fora dos stubs do ``requests``.
    ``None`` quando o raspador não definiu timeout.
    """
    return cast("Any", request).req_kwargs.get("timeout")


def urlencoded_body_subset_matcher(expected: Mapping[str, str | list[str]]):
    """``responses`` matcher that checks only a subset of urlencoded body fields.

    ``responses.matchers.urlencoded_params_matcher`` requires the full body;
    use this when the scraper sends hidden/dynamic fields (CSRF tokens,
    ViewState, crypto tokens) that the contract should not pin down.

    Quando ``expected[k]`` e ``list[str]``, compara como conjunto contra
    todas as ocorrencias do campo no body (multi-value, ex.:
    ``menuinicial:relatorList=v1&menuinicial:relatorList=v2``). Quando e
    ``str``, compara contra a primeira ocorrencia — comportamento
    historico, preservado para os chamadores existentes.
    """
    def matcher(request):
        parsed_raw = parse_qs(corpo_enviado(request), keep_blank_values=True)
        missing: dict = {}
        for k, expected_v in expected.items():
            actual = parsed_raw.get(k, [])
            if isinstance(expected_v, list):
                if sorted(actual) != sorted(expected_v):
                    missing[k] = (expected_v, actual)
            else:
                actual_scalar = actual[0] if actual else ""
                if actual_scalar != expected_v:
                    missing[k] = (expected_v, actual_scalar)
        if missing:
            return False, f"body fields mismatch: {missing}"
        return True, ""
    return matcher


def corpo_form_parcial_matcher(esperado: Mapping[str, str]):
    """Matcher do ``responses`` que confere só alguns campos de um corpo de formulário.

    Cada campo de ``esperado`` precisa estar no corpo com exatamente aquele
    valor; os demais campos (ViewState, tokens) ficam livres. Difere de
    :func:`urlencoded_body_subset_matcher` em dois pontos: campo ausente não
    casa com ``""``, e campo repetido vale pela última ocorrência, como em
    :func:`corpo_form_enviado`.
    """
    def matcher(request: PreparedRequest) -> tuple[bool, str]:
        enviado = corpo_form_enviado(request)
        for campo, valor in esperado.items():
            if enviado.get(campo) != valor:
                return False, f"expected {campo!r}={valor!r}, got {enviado.get(campo)!r}"
        return True, ""
    return matcher


def assert_unknown_kwarg_raises(
    method: Callable,
    kwarg: str | Sequence[str],
    *args,
    valor: str = "x",
    rotulo: str | None = None,
    exata: bool = False,
    **extra_kwargs,
) -> None:
    """Confirma que ``kwarg`` dispara ``TypeError`` canonico no endpoint.

    Centraliza o regex que da match na mensagem de
    :func:`juscraper.utils.params.raise_on_extra_kwargs`. Mudancas no
    formato da mensagem (aspas, prefixo, sufixo de close-match) ficam
    em uma linha so, em vez de espalhadas em 30+ tribunais.

    Cobre dois cenarios — mecanicamente identicos, ambos sao
    ``extra_forbidden`` puro do pydantic:

    - **Filtros de data nao suportados pelo backend** (issue #186):
      tribunais que so aceitam um dos intervalos
      (``data_julgamento_*`` xor ``data_publicacao_*``) rejeitam o
      oposto via ``extra="forbid"`` do schema.
    - **Kwargs desconhecidos genericos** (issue #84): typos ou
      parametros inventados (ex.: ``parametro_bobo``) sao rejeitados
      pelo mesmo mecanismo.

    Args:
        method (callable): Bound method publico do scraper (e.g.,
            ``jus.scraper("tjmt").cjsg``).
        kwarg (str | Sequence[str]): Nome do kwarg que deve ser rejeitado
            (e.g., ``"data_publicacao_inicio"`` para datas,
            ``"parametro_bobo"`` para typos genericos), ou uma sequencia de
            nomes, que a mensagem deve listar na mesma ordem.
        *args: Argumentos posicionais propagados para ``method``
            (tipicamente ``"pesquisa"``).
        valor (str): Valor passado em cada ``kwarg``. Cosmetico — o
            ``TypeError`` e emitido pelo pydantic *antes* de qualquer
            validacao de formato, entao qualquer string serve. Default
            ``"x"``.
        rotulo (str | None): Rotulo do metodo que deve abrir a mensagem
            (ex.: ``"TJPIScraper.cjsg()"``). Default ``None`` (confere so o
            sufixo canonico).
        exata (bool): Se ``True``, a mensagem termina nos nomes, sem sugestao
            ``(você quis dizer ...)`` nem outro sufixo. Default ``False``.
        **extra_kwargs: Kwargs extras propagados para ``method`` — util
            para cenarios que precisam de filtros adicionais (ex.: TJSP
            auto_chunk exige uma janela longa de ``data_julgamento_*``
            para acionar o sniff; eSAJ exige ``paginas=1``).
    """
    nomes = [kwarg] if isinstance(kwarg, str) else list(kwarg)
    listados = ", ".join(re.escape(repr(nome)) for nome in nomes)
    pattern = rf"got unexpected keyword argument\(s\): {listados}"
    if rotulo is not None:
        pattern = rf"^{re.escape(rotulo)} {pattern}"
    if exata:
        pattern += r"\Z"
    with pytest.raises(TypeError, match=pattern):
        method(*args, **{**dict.fromkeys(nomes, valor), **extra_kwargs})


_MOJIBAKE_RE = re.compile("[\u00c3\u00c2][\u0080-\u00bf]")


def assert_no_mojibake(texto: str, *, contexto: str = "") -> None:
    """Falha se ``texto`` tiver mojibake de UTF-8 lido como latin-1.

    Detecta o padrao estrutural do double-encoding: um byte lider ``Ã``
    (0xC3) ou ``Â`` (0xC2) seguido de um caractere na faixa U+0080-U+00BF
    — a assinatura de ``texto.encode("utf-8").decode("latin-1")``. Cobre
    qualquer acento do portugues (``petição`` -> ``petiÃ§Ã£o``,
    ``comunicação`` -> ``comunicaÃ§Ã£o``), nao so ``ç``/``ã``.

    Diferente de ``"Ã" not in texto``, nao da falso positivo em texto
    legitimo em maiusculas (``"DECISÃO"``, ``"SÃO PAULO"``), onde ``Ã`` e
    seguido de letra ASCII — fora da faixa de mojibake.

    Args:
        texto (str): Texto a inspecionar (descricoes de movs concatenadas,
            fragmento bruto, etc.).
        contexto (str): Rotulo opcional incluido na mensagem de falha para
            localizar a origem (ex.: ``"fetch_movs_page"``).
    """
    match = _MOJIBAKE_RE.search(texto)
    suffix = f" ({contexto})" if contexto else ""
    assert match is None, (
        f"mojibake detectado{suffix}: {match.group()!r} — "
        "fragmento UTF-8 decodificado como latin-1"
    )


def query_param_subset_matcher(expected: dict[str, str]):
    """``responses`` matcher that checks only a subset of query-string params."""
    def matcher(request):
        qs = parse_qs(urlparse(request.url).query, keep_blank_values=True)
        flat = {k: v[0] if v else "" for k, v in qs.items()}
        missing = {
            k: (expected[k], flat.get(k))
            for k in expected
            if flat.get(k) != expected[k]
        }
        if missing:
            return False, f"query params mismatch: {missing}"
        return True, ""
    return matcher


PDF_FALSO = b"%PDF-1.4\n% corpo curto: os testes so conferem o prefixo e a gravacao\n"
"""Corpo do ``getPDF.do`` nos contratos do acórdão; o parser não lê o PDF."""


def registrar_rota_acordao(tribunal: str, cenario: str, base_url: str, cposg: str) -> None:
    """Registra no ``responses`` as páginas gravadas por ``capture_acordao_samples``.

    Cada arquivo de ``tests/<tribunal>/samples/acordao/<cenario>/`` vira a
    resposta da URL que o gerou, com os parâmetros conferidos. Página ``n`` de
    movimentações casa com o cursor gravado na página ``n - 1``. A resposta
    do ``verificarAcessoMovimentacao.do`` com a janela de senha sai com o 403
    que o eSAJ manda. ``getPDF.do`` devolve :data:`PDF_FALSO`.
    """
    pasta = _SAMPLES_ROOT / tribunal / "samples" / "acordao" / cenario
    raiz = f"{base_url}{cposg}"
    # O cposg e a pasta digital declaram UTF-8; sem o charset, o requests leria latin-1.
    html = "text/html;charset=UTF-8"
    for arquivo in sorted(pasta.iterdir()):
        nome, corpo = arquivo.stem, arquivo.read_bytes()
        if nome == "search":
            responses.add(responses.GET, f"{raiz}search.do", body=corpo, content_type=html)
        elif nome.startswith("show_"):
            responses.add(
                responses.GET, f"{raiz}show.do", body=corpo, content_type=html,
                match=[matchers.query_param_matcher({"processo.codigo": nome.removeprefix("show_")})],
            )
        elif nome.startswith("movimentacoes_"):
            cd, indice = nome.removeprefix("movimentacoes_").rsplit("_", 1)
            params = {"cdProcesso": cd}
            if indice != "0":
                anterior = (pasta / f"movimentacoes_{cd}_{int(indice) - 1}.html").read_text(encoding="utf-8")
                params["cursor"] = parse_cursor(anterior) or ""
            responses.add(
                responses.GET, f"{raiz}carregarMovimentacoesAjax.do", body=corpo, content_type=html,
                match=[matchers.query_param_matcher(params)],
            )
        elif nome.startswith("verificar_acesso_"):
            cd, documento = nome.removeprefix("verificar_acesso_").rsplit("_", 1)
            responses.add(
                responses.GET, f"{raiz}verificarAcessoMovimentacao.do", body=corpo, content_type=html,
                status=403 if b"senhaProcesso" in corpo else 200,
                match=[matchers.query_param_matcher({
                    "cdDocumento": documento, "origemRecurso": "M", "cdProcesso": cd, "conversationId": "",
                })],
            )
            texto = corpo.decode("utf-8").strip()
            if texto.startswith("http"):
                responses.add(
                    responses.GET, texto, body=(pasta / f"pasta_{cd}_{documento}.html").read_bytes(),
                    content_type=html,
                )
    responses.add(responses.GET, f"{base_url}pastadigital/getPDF.do", body=PDF_FALSO)
