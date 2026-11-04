"""Shared helpers for juscraper tests.

Centralizes fixture loading and ``responses`` matchers. Used by parser tests
(direct call), contract tests (via ``responses.add(body=load_sample(...))``)
and granular tests.

Examples
--------
>>> from tests._helpers import load_sample
>>> html = load_sample("tjsp", "cjsg/results_normal.html")
"""
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
import responses
from responses import matchers

from juscraper.courts._esaj.acordao import parse_cursor

_SAMPLES_ROOT = Path(__file__).parent


def load_sample(tribunal: str, relative_path: str, *, encoding: str = "utf-8") -> str:
    """Load a sample fixture as string.

    Parameters
    ----------
    tribunal : str
        Court directory under ``tests/`` (e.g., ``"tjsp"``, ``"tjac"``).
    relative_path : str
        Path inside ``tests/<tribunal>/samples/`` (e.g., ``"cjsg/results_normal.html"``).
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
        body = request.body or b""
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        parsed_raw = parse_qs(body, keep_blank_values=True)
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


def assert_unknown_kwarg_raises(
    method: Callable,
    kwarg: str,
    *args,
    valor: str = "x",
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
        kwarg (str): Nome do kwarg que deve ser rejeitado (e.g.,
            ``"data_publicacao_inicio"`` para datas, ``"parametro_bobo"``
            para typos genericos).
        *args: Argumentos posicionais propagados para ``method``
            (tipicamente ``"pesquisa"``).
        valor (str): Valor passado em ``kwarg``. Cosmetico — o
            ``TypeError`` e emitido pelo pydantic *antes* de qualquer
            validacao de formato, entao qualquer string serve. Default
            ``"x"``.
        **extra_kwargs: Kwargs extras propagados para ``method`` — util
            para cenarios que precisam de filtros adicionais (ex.: TJSP
            auto_chunk exige uma janela longa de ``data_julgamento_*``
            para acionar o sniff; eSAJ exige ``paginas=1``).
    """
    pattern = rf"got unexpected keyword argument\(s\): '{re.escape(kwarg)}'"
    with pytest.raises(TypeError, match=pattern):
        method(*args, **{kwarg: valor, **extra_kwargs})


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
