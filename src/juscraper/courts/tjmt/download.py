"""
Baixa resultados brutos da pesquisa de jurisprudência do TJMT.
"""
import math
import re
import unicodedata
from collections import deque
from collections.abc import Callable, Iterator
from datetime import date
from urllib.parse import urljoin, urlparse

import requests

from juscraper.core.http import RequestFn
from juscraper.utils.pagination import baixar_paginas_pedidas, recusar_alem_do_teto
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


class _TJMTConfigRejected(Exception):
    """Sinaliza 401/403 da API para renovação local da configuração do TJMT."""


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
    home = request_fn("GET", PORTAL_URL, perfil="configuracao").text
    initial_resources = _SCRIPT_SRC_RE.findall(home) + _MODULE_PRELOAD_RE.findall(home)
    resources = deque(urljoin(PORTAL_URL, src) for src in initial_resources)
    visited: set[str] = set()

    while resources and len(visited) < MAX_CONFIG_RESOURCES:
        resource = resources.popleft()
        parsed = urlparse(resource)
        if parsed.scheme != "https" or parsed.hostname != PORTAL_HOST or resource in visited:
            continue
        visited.add(resource)
        script = request_fn("GET", resource, perfil="configuracao").text
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
    classe: str | None,
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
    if classe is not None:
        # O nome engana: no portal, ``fqTipoProcesso`` é a faceta de classe
        # (``facetTipoProcesso``) e filtra por ``nomeClasse``. ``fqClasse``
        # pertence a outro endpoint do bundle e é ignorado em ``/consulta``.
        params["fqTipoProcesso"] = classe
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
    """Normaliza nome textual de relator, órgão julgador ou classe."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        raise TypeError(f"{name} deve ser um nome textual, não um identificador numérico.")
    if not isinstance(value, str):
        raise TypeError(f"{name} deve ser informado como texto.")
    normalized = " ".join(value.strip().split())
    normalized = "".join(
        # NFD, não NFKD: os nomes da API mantêm "ª" e "º" ("2ª CAMARA").
        char for char in unicodedata.normalize("NFD", normalized)
        if not unicodedata.combining(char)
    ).upper()
    if normalized.isdigit():
        raise ValueError(f"{name} não aceita identificadores numéricos.")
    return normalized or None


def _normalize_nome_unico(value: str | None, name: str) -> str | None:
    """Normaliza ``relator`` ou ``orgao_julgador`` e recusa nome com vírgula.

    Medido em 16/11/2026: a API parte ``fqRelator`` e ``fqOrgaoJulgador`` na
    vírgula e soma os resultados de cada parte (dois relatores com 1 e 152
    resultados devolveram 153). Nenhum nome das facetas tem vírgula, então
    ela só pode vir de um engano, que filtraria por outros nomes.
    """
    if isinstance(value, str) and "," in value:
        raise ValueError(
            f"{name} não aceita vírgula: a API do TJMT a lê como separador de nomes "
            "e somaria os resultados de cada parte. Informe um nome por consulta."
        )
    return _normalize_text_filter(value, name)


# Vírgula de largura inteira (U+FF0C). Medido em 16/11/2026 em
# ``fqTipoProcesso``: a API parte o valor na vírgula ASCII e só depois equipara
# as duas, então é assim que um nome de classe com vírgula chega inteiro ao
# índice. Barra, aspas, ``%2C`` e o código da classe não filtram.
_VIRGULA_NO_NOME = "\uff0c"


def _normalize_classe(value: str | list[str] | None) -> str | None:
    """Normaliza um nome de classe, ou uma lista deles, para ``fqTipoProcesso``.

    Medido em 16/11/2026: a API parte ``fqTipoProcesso`` na vírgula e soma as
    classes (37.389 + 1.727 = 39.116 em "dano moral"). A lista vai separada
    por vírgula, e a vírgula de dentro de um nome, como
    :data:`_VIRGULA_NO_NOME`. Só a lista aceita nome com vírgula: numa string,
    ela tanto pode ser do nome quanto de uma lista escrita como texto, que
    devolveria busca vazia.
    """
    if isinstance(value, str):
        if "," in value:
            raise ValueError(
                "classe em texto não aceita vírgula. Para várias classes, passe uma lista "
                '(classe=["Apelação Cível", "Agravo de Instrumento"]); para uma classe com vírgula '
                "no nome, passe-a dentro de uma lista."
            )
        return _normalize_text_filter(value, "classe")
    if value is None:
        return None
    nomes = [_normalize_text_filter(nome, "classe") for nome in value]
    if not any(nomes):
        raise ValueError("classe recebeu uma lista sem nomes; use None para não filtrar.")
    return ",".join(nome.replace(",", _VIRGULA_NO_NOME) for nome in nomes if nome)


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


def _validate_download_inputs(quantidade: int, tipo_consulta: str) -> None:
    """Valida tamanho de página e tipo antes de iniciar requisições HTTP."""
    _validate_page_size(quantidade)
    if tipo_consulta not in {"Acordao", "DecisaoMonocratica"}:
        raise ValueError(f"Tipo de consulta não suportado pelo TJMT: {tipo_consulta}.")


def _initial_api_config(
    request_fn: RequestFn,
    api_config_provider: Callable[..., dict[str, str]] | None,
) -> dict[str, str]:
    """Usa a configuração em cache do scraper ou descobre a atual."""
    if api_config_provider is None:
        return _get_api_config(request_fn)
    return api_config_provider()


def _apply_api_config(session: requests.Session, config: dict[str, str]) -> None:
    """Aplica os headers da configuração pública atual da API TJMT."""
    session.headers.update({
        "token": config["token"],
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://jurisprudencia.tjmt.jus.br/",
    })


def _raise_if_config_rejected(response: requests.Response) -> None:
    """Interrompe o retry HTTP comum para tratar auth expirada localmente."""
    if response.status_code in {401, 403}:
        raise _TJMTConfigRejected


def _request_api_page(
    request_fn: RequestFn,
    api_url: str,
    params: dict,
    session: requests.Session,
    api_config_provider: Callable[..., dict[str, str]] | None,
) -> requests.Response:
    """Consulta uma página e, após 401/403, renova a configuração uma vez.

    A consulta repetida usa a política de retry comum; um novo 401/403
    propaga como ``HTTPError`` ou ``RetryExhaustedError``. ``api_url`` não
    muda na renovação, porque ``_validate_api_config`` só aceita
    ``PRODUCTION_API_URL``.
    """
    request_kwargs = {"params": params, "perfil": "busca"}
    if api_config_provider is None:
        return request_fn("GET", f"{api_url}/consulta", **request_kwargs)

    try:
        return request_fn(
            "GET",
            f"{api_url}/consulta",
            on_response=_raise_if_config_rejected,
            **request_kwargs,
        )
    except _TJMTConfigRejected:
        _apply_api_config(session, api_config_provider(force_refresh=True))
        return request_fn("GET", f"{api_url}/consulta", **request_kwargs)


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
    classe: str | list[str] | None = None,
    request_fn: RequestFn,
    session: requests.Session,
    api_config_provider: Callable[..., dict[str, str]] | None = None,
) -> list:
    """Baixa resultados JSON brutos da API de jurisprudência do TJMT.

    Args:
        pesquisa: Termo de pesquisa.
        paginas: Páginas a baixar, 1-based, como ``range`` ou ``list``. ``None``
            baixa todas, até o teto de ``MAX_RESULTS`` resultados. Chega já
            validado pelo método público (``normalize_paginas`` e
            ``PaginasMixin``): ``int`` vira ``range`` e ficam recusados
            ``bool``, página ``0`` ou negativa e seleção vazia.
        tipo_consulta: ``"Acordao"`` ou ``"DecisaoMonocratica"``.
        data_publicacao_inicio: Data inicial de publicação.
        data_publicacao_fim: Data final de publicação, inclusiva.
        relator: Nome do relator, normalizado sem acento e em maiúsculas.
            Com vírgula, levanta ``ValueError``.
        orgao_julgador: Nome do órgão julgador, com a mesma normalização.
        tipo_processo: ``"Civel"``, ``"Cível"`` ou ``"Criminal"``.
        thesaurus: Define se a pesquisa deve usar sinônimos.
        quantidade_por_pagina: Itens por página (padrão 10), no máximo
            ``MAX_RESULTS``.
        classe: Nome da classe processual, ou lista de nomes, com a mesma
            normalização de ``relator``.
        request_fn: Callable HTTP que trata retries e ``raise_for_status``,
            normalmente ``TJMTScraper._request_with_retry`` (via
            ``core.http.HTTPScraper``), centralizando o backoff exponencial
            para 429/5xx.
        session: ``requests.Session`` compartilhada por ``HTTPScraper``;
            recebida explicitamente para manter os headers ``Token``,
            ``Accept`` e ``Referer`` obtidos por ``_get_api_config``. As
            requisições subsequentes via ``request_fn`` usam essa mesma sessão.
        api_config_provider: Provedor interno opcional de configuração em
            cache. Quando omitido, a função descobre a configuração como antes.

    Avisos:
        ``UserWarning``: com ``paginas=None``, quando a consulta passa do teto
        de ``MAX_RESULTS`` resultados que a API devolve; baixa só as páginas
        que cabem no teto.

    Returns:
        Lista de dicionários JSON brutos, um por página.
    """
    _validate_download_inputs(quantidade_por_pagina, tipo_consulta)

    def _n_pags(total: int) -> int:
        return math.ceil(total / quantidade_por_pagina) if total else 1

    # A API responde HTTP 500 além do teto; a página pedida além dele é
    # recusada aqui, antes de qualquer requisição.
    teto = MAX_RESULTS // quantidade_por_pagina
    recusar_alem_do_teto(paginas, teto, tribunal="TJMT")
    data_publicacao_inicio = _to_tjmt_date(data_publicacao_inicio)
    data_publicacao_fim = _to_end_of_day(data_publicacao_fim)
    relator = _normalize_nome_unico(relator, "relator")
    orgao_julgador = _normalize_nome_unico(orgao_julgador, "orgao_julgador")
    tipo_processo = _normalize_tipo_processo(tipo_processo)
    classe = _normalize_classe(classe)
    cfg = _initial_api_config(request_fn, api_config_provider)
    api_url = cfg["api_url"]
    _apply_api_config(session, cfg)

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
            classe=classe,
        )
        resp = _request_api_page(request_fn, api_url, params, session, api_config_provider)
        try:
            data = resp.json()
        except ValueError as exc:
            raise TJMTResponseError("Resposta da API do TJMT não contém JSON válido.") from exc
        return _validate_response(data, tipo_consulta)

    pages = baixar_paginas_pedidas(
        paginas,
        lambda pagina: _fetch_page(pagina - 1),  # a API conta as páginas a partir de 0
        lambda resposta: _n_pags(resposta[1]),
        tribunal="TJMT",
        sleep_time=1,
        teto=teto,
    )
    return [page for page, _ in pages]
