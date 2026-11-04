"""
Baixa resultados brutos da pesquisa de jurisprudência do TJMT.
"""
import math
import re
import time
import unicodedata
from collections import deque
from collections.abc import Iterator
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from tqdm import tqdm

from juscraper.core.avisos import avisar
from juscraper.core.http import RequestFn
from juscraper.utils.params import coerce_brazilian_date

PORTAL_URL = "https://jurisprudencia.tjmt.jus.br/"
PORTAL_HOST = "jurisprudencia.tjmt.jus.br"
PRODUCTION_API_URL = "https://hellsgate.tjmt.jus.br/jurisprudencia"
MAX_CONFIG_RESOURCES = 32
DEFAULT_PAGE_SIZE = 10
# A API devolve no máximo os 10.000 primeiros resultados de uma consulta.
# Medido em 04/11/2026: quando indicePagina * quantidadePagina +
# quantidadePagina passa de 10.000, a resposta é HTTP 500 com corpo vazio
# (com 10 por página, o índice 999 responde e o 1000 falha; com 100, o 99
# responde e o 100 falha).
MAX_RESULTS = 10_000


class TJMTConfigError(ValueError):
    """Indica que a configuração pública do TJMT está ausente ou inválida."""


class TJMTResponseError(ValueError):
    """Indica que a API de jurisprudência retornou uma resposta inválida."""


_SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)", re.IGNORECASE)
_MODULE_PRELOAD_RE = re.compile(
    r"<link(?=[^>]+\brel=[\"']modulepreload[\"'])(?=[^>]+\bhref=[\"']([^\"']+)[\"'])[^>]*>",
    re.IGNORECASE,
)
_IMPORT_RE = re.compile(
    r"(?:from\s*|import\s*(?:\(\s*)?)[\"']([^\"']+\.js(?:\?[^\"']*)?)[\"']"
)
_CONFIG_PROPERTY_RE = re.compile(
    r"(?<![\w$])(?P<name_quote>[\"']?)(?P<name>api_url|api_hellsgate_token)(?P=name_quote)\s*:\s*"
    r"(?P<quote>[\"'])(?P<value>.*?)(?P=quote)"
)


def _skip_js_string(script: str, start: int) -> int:
    """Retorna o índice após uma string JavaScript entre aspas."""
    quote = script[start]
    escaped = False
    index = start + 1
    while index < len(script):
        char = script[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return index + 1
        index += 1
    return len(script)


def _skip_js_comment(script: str, start: int) -> int:
    """Retorna o índice após um comentário JavaScript."""
    if script.startswith("//", start):
        newline = script.find("\n", start + 2)
        return len(script) if newline == -1 else newline
    end = script.find("*/", start + 2)
    return len(script) if end == -1 else end + 2


def _iter_js_object_bodies(script: str) -> Iterator[str]:
    """Produz corpos de objetos JavaScript ignorando chaves em strings e comentários."""
    stack: list[int] = []
    index = 0
    while index < len(script):
        char = script[index]
        if char in "\"'`":
            index = _skip_js_string(script, index)
            continue
        if script.startswith("//", index) or script.startswith("/*", index):
            index = _skip_js_comment(script, index)
            continue
        if char == "{":
            stack.append(index)
        elif char == "}" and stack:
            start = stack.pop()
            yield script[start + 1:index]
        index += 1


def _extract_top_level_config(body: str) -> dict[str, str]:
    """Extrai propriedades de configuração pertencentes diretamente a um objeto."""
    values: dict[str, str] = {}
    depth = 0
    index = 0
    while index < len(body):
        if body.startswith("//", index) or body.startswith("/*", index):
            index = _skip_js_comment(body, index)
            continue
        if depth == 0:
            match = _CONFIG_PROPERTY_RE.match(body, index)
            if match is not None:
                values[match.group("name")] = match.group("value")
                index = match.end()
                continue
        char = body[index]
        if char in "\"'`":
            index = _skip_js_string(body, index)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1
    return values


def _extract_api_config(script: str) -> dict[str, str] | None:
    """Extrai as duas configurações da API do mesmo objeto JavaScript."""
    for body in _iter_js_object_bodies(script):
        config = _extract_top_level_config(body)
        if "api_url" in config and "api_hellsgate_token" in config:
            return config
    return None


def _validate_api_config(config: dict[str, str]) -> dict[str, str]:
    """Valida a URL descoberta sem expor o token."""
    api_url = config.get("api_url", "").strip()
    token = config.get("api_hellsgate_token", "").strip()
    if api_url != PRODUCTION_API_URL:
        raise TJMTConfigError("URL da API do TJMT ausente ou fora do endpoint de produção esperado.")
    if not token:
        raise TJMTConfigError("Token da API do TJMT ausente na configuração pública.")
    return {"api_url": api_url, "token": token}


def _get_api_config(request_fn: RequestFn) -> dict:
    """Descobre e valida a configuração pública atual da API."""
    home = request_fn("GET", PORTAL_URL, timeout=30).text
    initial_resources = _SCRIPT_SRC_RE.findall(home) + _MODULE_PRELOAD_RE.findall(home)
    resources = deque(urljoin(PORTAL_URL, src) for src in initial_resources)
    visited: set[str] = set()

    while resources and len(visited) < MAX_CONFIG_RESOURCES:
        resource = resources.popleft()
        parsed = urlparse(resource)
        if parsed.scheme != "https" or parsed.hostname != PORTAL_HOST or resource in visited:
            continue
        visited.add(resource)
        script = request_fn("GET", resource, timeout=30).text
        config = _extract_api_config(script)
        if config is not None:
            return _validate_api_config(config)
        resources.extend(urljoin(resource, imported) for imported in _IMPORT_RE.findall(script))

    if len(visited) >= MAX_CONFIG_RESOURCES:
        raise TJMTConfigError("Limite de recursos excedido ao descobrir a configuração do TJMT.")
    raise TJMTConfigError("Configuração da API do TJMT não encontrada nos scripts públicos.")


def _build_params(
    pesquisa: str,
    pagina: int,
    quantidade: int,
    tipo_consulta: str,
    thesaurus: bool,
    data_publicacao_inicio: str | None,
    data_publicacao_fim: str | None,
    relator: str | None,
    orgao_julgador: str | None,
    tipo_processo: str | None,
) -> dict:
    """Monta os parâmetros da query para o endpoint de consulta."""
    params = {
        "indicePagina": pagina,
        "quantidadePagina": quantidade,
        "tipoConsulta": {"Acordao": "1", "DecisaoMonocratica": "2"}[tipo_consulta],
        "termoDeBusca": pesquisa,
        "tipoBusca": "1",
        "OrdenarPor": "Relevancia",
        "Decrescente": "true",
        "thesaurus": str(thesaurus).lower(),
        "exibirArquivados": "true",
    }
    if data_publicacao_inicio is not None:
        params["periodoDataDe"] = data_publicacao_inicio
    if data_publicacao_fim is not None:
        params["periodoDataAte"] = data_publicacao_fim
    if relator is not None:
        params["fqRelator"] = relator
    if orgao_julgador is not None:
        params["fqOrgaoJulgador"] = orgao_julgador
    if tipo_processo is not None:
        params["tipoProcesso"] = tipo_processo
    return params


def _validate_response(data: object, tipo_consulta: str) -> tuple[dict, int]:
    """Valida o envelope da API e retorna a página e sua contagem específica."""
    if not isinstance(data, dict):
        raise TJMTResponseError("Resposta da API do TJMT não é um objeto JSON.")
    if data.get("success") is not True:
        raise TJMTResponseError("API de jurisprudência do TJMT retornou erro.")
    if data.get("errorMessage") is not None:
        raise TJMTResponseError("API de jurisprudência do TJMT retornou uma mensagem de erro.")
    value = data.get("value")
    if not isinstance(value, dict) or not isinstance(value.get("resultados"), list):
        raise TJMTResponseError("Resposta da API do TJMT não contém value.resultados válido.")
    count_key = "countAcordaoDocumento" if tipo_consulta == "Acordao" else "countDecisaoMonocratica"
    count = value.get(count_key)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise TJMTResponseError(f"Resposta da API do TJMT não contém {count_key} válido.")
    return data, count


def _normalize_text_filter(value: str | int | None, name: str) -> str | None:
    """Normaliza nome textual de relator ou órgão julgador."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        raise TypeError(f"{name} deve ser um nome textual, não um identificador numérico.")
    if not isinstance(value, str):
        raise TypeError(f"{name} deve ser informado como texto.")
    normalized = " ".join(value.strip().split())
    normalized = "".join(
        char for char in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(char)
    ).upper()
    if normalized.isdigit():
        raise ValueError(f"{name} não aceita identificadores numéricos.")
    return normalized or None


def _normalize_tipo_processo(value: str | None) -> str | None:
    """Converte o tipo público de processo para o código da API."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise TypeError("tipo_processo deve ser informado como texto.")
    try:
        return {"Criminal": "1", "Civel": "2", "Cível": "2"}[value]
    except KeyError as exc:
        raise ValueError(f"tipo_processo desconhecido: {value}.") from exc


def _to_tjmt_date(value) -> str | None:
    """Converte uma data aceita pelo projeto para ISO e valida seu valor."""
    normalized = coerce_brazilian_date(value, "%Y-%m-%d")
    if normalized is None:
        return None
    if normalized == "":
        return ""
    if not isinstance(normalized, str):
        raise TypeError(f"Data deve ser texto ou data, recebido: {value!r}.")
    try:
        return date.fromisoformat(normalized).isoformat()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Data inválida para o TJMT: {value!r}.") from exc


def _to_end_of_day(value) -> str | None:
    """Converte a data final inclusiva no último segundo desse dia.

    A API compara ``periodoDataAte`` com o instante informado, inclusive, e lê
    uma data sem hora como meia-noite. Enviar só o dia perderia o que foi
    publicado nele depois da meia-noite; somar um dia traria o que foi
    publicado à meia-noite do dia seguinte. ``T23:59:59`` cobre o dia pedido
    inteiro e nada além dele.
    """
    normalized = _to_tjmt_date(value)
    if not normalized:
        return normalized
    return f"{normalized}T23:59:59"


def _validate_page_size(quantidade: int) -> None:
    """Valida o tamanho de página contra o domínio aceito pela API."""
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise TypeError("tamanho_pagina deve ser um inteiro positivo.")
    if quantidade < 1:
        raise ValueError("tamanho_pagina deve ser maior que zero.")
    if quantidade > MAX_RESULTS:
        raise ValueError(
            f"tamanho_pagina deve ser no máximo {MAX_RESULTS}, o teto de resultados "
            "que a API do TJMT devolve por consulta."
        )


def _as_page_list(paginas) -> list[int]:
    """Converte ``paginas`` (inteiro ou iterável) em lista de páginas 1-based."""
    if isinstance(paginas, bool):
        raise TypeError("paginas deve conter inteiros positivos.")
    if isinstance(paginas, int):
        if paginas < 1:
            raise ValueError("paginas deve conter apenas valores maiores que zero.")
        paginas = range(1, paginas + 1)
    try:
        paginas_list = list(paginas)
    except TypeError as exc:
        raise TypeError("paginas deve conter inteiros positivos.") from exc
    if any(isinstance(pagina, bool) or not isinstance(pagina, int) for pagina in paginas_list):
        raise TypeError("paginas deve conter inteiros positivos.")
    if any(pagina < 1 for pagina in paginas_list):
        raise ValueError("paginas deve conter apenas valores maiores que zero.")
    return paginas_list


def _reject_pages_beyond_limit(paginas_list: list[int], quantidade: int) -> None:
    """Rejeita páginas que a API responderia com HTTP 500 por passarem do teto."""
    limite = _max_paginas(quantidade)
    alem_do_limite = sorted(pagina for pagina in paginas_list if pagina > limite)
    if alem_do_limite:
        raise ValueError(
            f"A API do TJMT devolve só os {MAX_RESULTS} primeiros resultados de uma "
            f"consulta; com tamanho_pagina={quantidade}, a última página alcançável é "
            f"a {limite}, e foram pedidas {alem_do_limite[:5]}. Restrinja a busca por "
            "data de publicação ou relator para alcançar os demais."
        )


def _validate_download_inputs(quantidade: int, paginas, tipo_consulta: str) -> list[int] | None:
    """Valida paginação e tipo antes de iniciar requisições HTTP."""
    _validate_page_size(quantidade)
    if tipo_consulta not in {"Acordao", "DecisaoMonocratica"}:
        raise ValueError(f"Tipo de consulta não suportado pelo TJMT: {tipo_consulta}.")
    if paginas is None:
        return None
    paginas_list = _as_page_list(paginas)
    _reject_pages_beyond_limit(paginas_list, quantidade)
    return paginas_list


def _max_paginas(quantidade: int) -> int:
    """Retorna a última página, 1-based, que cabe no teto de resultados da API."""
    return MAX_RESULTS // quantidade


def cjsg_download(
    pesquisa: str,
    paginas=None,
    tipo_consulta: str = "Acordao",
    data_publicacao_inicio: str | None = None,
    data_publicacao_fim: str | None = None,
    relator: str | None = None,
    orgao_julgador: str | None = None,
    tipo_processo: str | None = None,
    thesaurus: bool = False,
    quantidade_por_pagina: int = DEFAULT_PAGE_SIZE,
    *,
    request_fn: RequestFn,
    session: requests.Session,
) -> list:
    """Baixa resultados JSON brutos da API de jurisprudência do TJMT.

    Argumentos:
    pesquisa: Termo de pesquisa.
    paginas: Páginas a baixar, baseadas em 1. ``None`` baixa todas.
    tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.
    data_publicacao_inicio: Data inicial de publicação.
    data_publicacao_fim: Data final inclusiva de publicação.
    relator: Filtro pelo nome do relator.
    orgao_julgador: Filtro pela câmara julgadora.
    tipo_processo: ``"Cível"`` ou ``"Criminal"``.
    thesaurus: Define se a pesquisa deve usar sinônimos.
    quantidade_por_pagina: Itens por página (padrão 10).
    request_fn: Callable HTTP que trata retries e ``raise_for_status`` —
        normalmente ``TJMTScraper._request_with_retry`` (via
        ``core.http.HTTPScraper``), centralizando o backoff exponencial
        para 429/5xx.
    session: ``requests.Session`` compartilhada por ``HTTPScraper``;
        recebida explicitamente para manter os headers ``Token``,
        ``Accept`` e ``Referer`` obtidos por ``_get_api_config``. As
        requisições subsequentes via ``request_fn`` usam essa mesma sessão.

    Avisos:
    ``UserWarning``: com ``paginas=None``, quando a consulta passa do teto
    de ``MAX_RESULTS`` resultados que a API devolve; baixa só as páginas
    que cabem no teto.

    Retorno:
    Lista de dicionários JSON brutos, um por página.
    """
    paginas_list = _validate_download_inputs(quantidade_por_pagina, paginas, tipo_consulta)
    data_publicacao_inicio = _to_tjmt_date(data_publicacao_inicio)
    data_publicacao_fim = _to_end_of_day(data_publicacao_fim)
    relator = _normalize_text_filter(relator, "relator")
    orgao_julgador = _normalize_text_filter(orgao_julgador, "orgao_julgador")
    tipo_processo = _normalize_tipo_processo(tipo_processo)
    cfg = _get_api_config(request_fn)
    api_url = cfg["api_url"]
    token = cfg["token"]

    session.headers.update({
        "token": token,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })

    def _fetch_page(pagina: int) -> tuple[dict, int]:
        params = _build_params(
            pesquisa=pesquisa,
            pagina=pagina,
            quantidade=quantidade_por_pagina,
            tipo_consulta=tipo_consulta,
            thesaurus=thesaurus,
            data_publicacao_inicio=data_publicacao_inicio,
            data_publicacao_fim=data_publicacao_fim,
            relator=relator,
            orgao_julgador=orgao_julgador,
            tipo_processo=tipo_processo,
        )
        resp = request_fn(
            "GET",
            f"{api_url}/consulta",
            params=params,
            timeout=60,
            expect_json=True,
        )
        try:
            data = resp.json()
        except ValueError as exc:
            raise TJMTResponseError("Resposta da API do TJMT não contém JSON válido.") from exc
        return _validate_response(data, tipo_consulta)

    if paginas_list is None:
        first, total = _fetch_page(0)
        resultados = [first]
        n_pags = math.ceil(total / quantidade_por_pagina) if total else 1
        limite = _max_paginas(quantidade_por_pagina)
        if n_pags > limite:
            n_pags = limite
            avisar(
                f"A consulta ao TJMT tem {total} resultados, e a API devolve no máximo "
                f"{MAX_RESULTS} por consulta; com tamanho_pagina={quantidade_por_pagina}, "
                f"vêm os {limite * quantidade_por_pagina} primeiros. "
                "Restrinja a busca por data de publicação (data_publicacao_inicio e "
                "data_publicacao_fim) ou por relator para alcançar os demais."
            )
        if n_pags > 1:
            for pagina in tqdm(range(1, n_pags), desc="Baixando páginas TJMT"):
                page, _ = _fetch_page(pagina)
                resultados.append(page)
                time.sleep(1)
        return resultados

    resultados = []
    for pagina in tqdm(paginas_list, desc="Baixando páginas TJMT"):
        page, _ = _fetch_page(pagina - 1)
        resultados.append(page)
        if len(paginas_list) > 1:
            time.sleep(1)
    return resultados
