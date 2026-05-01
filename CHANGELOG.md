# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Agregador `comunica_cnj` (`ComunicaCNJScraper`) para a API publica de Comunicacoes Processuais do CNJ (`https://comunicaapi.pje.jus.br/api/v1/comunicacao`). Metodo publico `listar_comunicacoes(pesquisa, paginas=None, data_disponibilizacao_inicio=None, data_disponibilizacao_fim=None, itens_por_pagina=100)` devolve `pandas.DataFrame` com uma linha por comunicacao. Validacao via schema pydantic `InputListarComunicacoesComunicaCNJ` (`extra="forbid"`); kwargs desconhecidos viram `TypeError`. `pesquisa` ausente vira `ValidationError`. Output schema `OutputListarComunicacoesComunicaCNJ` (`extra="allow"`, pivot `numero_processo`) registrado em `tests/schemas/test_output_parity.py`. Datas aceitam tanto ISO `YYYY-MM-DD` quanto formato brasileiro `DD/MM/YYYY` (convertido via `to_iso_date`); intervalo invalido vira `ValueError` via `validate_intervalo_datas`. Os nomes `data_disponibilizacao_inicio`/`_fim` foram escolhidos canonicos exatamente para evitar colisao com `data_inicio`/`data_fim` (alias deprecado de `data_julgamento_*` em `DEPRECATED_ALIASES`/`DATE_ALIASES`). Default `sleep_time=0.5` entre paginas, alinhado com `DatajudScraper`, para nao agredir a API publica do CNJ em batches grandes. Suite de contratos offline em `tests/comunica_cnj/test_listar_comunicacoes_contract.py` + `test_listar_comunicacoes_filters_contract.py` com 12 cenarios cobrindo multi-pagina, single page, no_results, propagacao de filtros e validacoes; o caso `comunica_cnj.listar_comunicacoes` esta registrado em `tests/schemas/test_docstring_parity.py::CASES`, fechando a paridade docstring/schema. Samples reais capturados via `python -m tests.fixtures.capture.comunica_cnj`. Modulo herdado do `bdcdo/raspe`, com correcao para a chave de resposta da API que mudou de `itens` (PT) para `items` (EN).
- `DatajudScraper.listar_processos` ganha filtros novos para expor recursos da API Elasticsearch do CNJ que antes nao eram acessiveis pela interface publica (refs #49): `data_ajuizamento_inicio`/`data_ajuizamento_fim` (range em `dataAjuizamento` com padrao dual-format ISO + compacto, mesmo da #51, mutuamente exclusivo com `ano_ajuizamento`); `tipos_movimentacao` (lista de nomes amigaveis — `decisao`/`sentenca`/`julgamento`/`tutela`/`transito_julgado` — resolvidos via novo mapping `TIPOS_MOVIMENTACAO` em `juscraper.aggregators.datajud.mappings`); `movimentos_codigo` (lista de codigos TPU diretos, concatenada com `tipos_movimentacao` quando ambos sao passados); `orgao_julgador` (`match` em `orgaoJulgador.nome`); `query` (override total da query Elasticsearch — passa um `dict` que vira a chave `query` do payload literalmente, mutuamente exclusivo com todos os filtros amigaveis acima e exigindo `tribunal` explicito; em troca, oferece paridade com requisicao direta a `/<alias>/_search` para `must_not`/`should`/`range` em campos arbitrarios/`wildcard`/`nested`/etc.). `data_inicio`/`data_fim` (alias generico do projeto que mapeia para `data_julgamento_*` em scrapers de jurisprudencia) **nao** e aceito aqui — o DataJud filtra por ajuizamento, nao julgamento, e o nome canonico explicito `data_ajuizamento_*` torna a semantica obvia. `extra="forbid"` faz quem usar o nome generico receber `TypeError` direto.
- `DatajudScraper.contar_processos` ganha paridade com `listar_processos` no escopo de #176: `data_ajuizamento_inicio`/`_fim`, `tipos_movimentacao`, `movimentos_codigo`, `orgao_julgador` e o escape-hatch `query` agora sao aceitos tambem na contagem. `InputContarProcessosDataJud` reusa os mesmos validators de `InputListarProcessosDataJud` (mutual exclusivity entre `ano_ajuizamento` e `data_ajuizamento_*`, formato ISO 8601, `query` exclusivo com filtros amigaveis e exigindo `tribunal`, `tipos_movimentacao` so aceita nomes mapeados); `build_contar_processos_payload` passa a delegar a montagem do `query` interno para o helper compartilhado `_build_query_amigavel`, garantindo que listar e contar produzam o mesmo body para os mesmos filtros.
- Schemas pydantic de Input e Output para **todos** os endpoints publicos implementados (nao stubs) nos 25 tribunais e 2 agregadores do juscraper. Tribunais ainda nao refatorados recebem schema-arquivo sem wiring — servem como documentacao executavel da API publica e ponto de encaixe para a refatoracao futura. Bases compartilhadas extraidas por evidencia concreta: `SearchBase` (25 ocorrencias de `pesquisa`/`paginas`), `DataJulgamentoMixin` (13 tribunais, agora incluindo TJPI apos #94/#125 e TJDFT apos #165), `DataPublicacaoMixin` (11, agora incluindo TJDFT apos #165), `CnjInputBase`/`OutputCnjConsultaBase` para endpoints de consulta processual, `OutputRelatoriaMixin` (>= 10 parsers cjsg) e `OutputDataPublicacaoMixin` (>= 9 parsers). Schemas wired no metodo publico via `extra="forbid"` em eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`/`cjpg`), familia 1C-a (TJRN/TJPA/TJRO/TJSC/TJPI `cjsg`), familia 1B parcial (TJDFT `cjsg`, TJES `cjsg`/`cjpg` — primeira leva de #165) e DataJud `listar_processos` — kwargs desconhecidos viram `TypeError`/`ValidationError` em vez de serem silenciosamente ignorados. Refs #93, #117, #120, #125, #152, #165.
- Utilities publicas em `juscraper.utils.params`: `apply_input_pipeline_search(schema_cls, method_name, *, pesquisa, paginas, kwargs, max_dias=None, origem_mensagem=None, **canonical_filters)` (pipeline canonico de validacao em uma chamada — `normalize_paginas` -> `normalize_datas` -> `pop_normalize_aliases` -> `validate_intervalo_datas` -> schema -> `raise_on_extra_kwargs`); `raise_on_extra_kwargs` (converte `ValidationError` com `extra_forbidden` em `TypeError` amigavel, com sugestao de typo via `difflib.get_close_matches` quando o `schema_cls` e fornecido — ex.: `data_juglamento_inicio` -> `(você quis dizer 'data_julgamento_inicio'?)`); `pop_normalize_aliases` + constantes `SEARCH_ALIASES`/`DATE_ALIASES`/`DATE_CANONICAL`; `to_iso_date` (contraparte de `to_br_date` para backends ISO-8601); `pop_deprecated_alias` e `resolve_deprecated_alias` (centralizam pop + warning + checagem de colisao). O parametro chama-se `origem_mensagem` (nao `origem`) porque varios scrapers usam `origem` como filtro do backend. Refs #84, #93, #119, #128.
- TJSP CJPG/CJSG: validacao de tamanho do campo `pesquisa` antes da requisicao. O backend do eSAJ trunca strings com mais de 120 caracteres silenciosamente; agora `cjpg_download` e `cjsg_download` levantam `QueryTooLongError` (subclasse de `ValueError`, exportada em `juscraper.courts.tjsp.exceptions`) quando o limite e excedido. Refs #35.
- Suite de contratos offline expandida cobrindo `cjsg` (e `cjpg` quando aplicavel) em TJAC, TJAL, TJAM, TJCE, TJMS, TJSP, TJDFT, TJBA, TJMT, TJAP, TJES, TJRS, TJRN, TJPA, TJRO, TJSC, TJPI, TJGO, TJPB, TJTO, TJPR, TJRR e TJMG, alem de TJSP `cpopg`/`cposg` (variantes `method='html'` e `'api'`) e DataJud `listar_processos`. Contratos via `responses` + samples reais versionados em `tests/<sigla>/samples/<endpoint>/`, validam schema minimo do DataFrame e payload enviado ao backend (`json_params_matcher`/`urlencoded_params_matcher`/`query_param_matcher`/`header_matcher`). Inclui regressoes para guard `QueryTooLongError` (TJSP), TLS adapter `SECLEVEL=1` (TJCE), aliases deprecados (`query`/`termo`/`data_inicio`/`data_fim`/`nr_processo`), fluxos com pre-request/CSRF/AJAX (TJPB, TJSC, TJPR, TJRR, TJMG — TJMG inclui mock do captcha numerico via `txtcaptcha`), `test_cjsg_unknown_kwarg_raises` em todos os tribunais 1C-a wired (mais TJDFT e TJES via #165), e cobertura release-tier (`tests/test_release_date_filter.py`, marker `release`) que exercita o filtro de janela de datas em todos os 25 tribunais. Helpers compartilhados em `tests._helpers` e fixtures em `tests/helpers.py` ficam disponiveis para futuros raspadores. Scripts de captura em `tests/fixtures/capture/<sigla>.py` importam helpers publicos de `download.py` evitando drift silencioso. Refs #19, #84, #93, #94, #104, #113, #116, #119, #120, #121, #122, #140, #144, #146, #147, #165.
- Helpers publicos de construcao de payload em `juscraper.courts.<sigla>.download`: `build_cjsg_payload` (TJDFT, TJRS, TJRN, TJPA, TJRO, TJGO, TJPB, TJTO), `build_cjsg_form_body`/`cjsg_url_for_page` (TJSC), `build_cjsg_params` (TJPI), `build_cjsg_inner_payload` (TJRS), `fetch_csrf_token` (TJPB), `post_cjsg` + `CJSG_HEADERS` (TJPA). Em DataJud, `juscraper.aggregators.datajud.download.build_listar_processos_payload`. Compartilhados com os scripts de captura, atendem a regra "single source of truth do body" — capture e producao falham juntos quando o body real do scraper muda.

### Changed

- TJES `cjsg` / `cjpg`: filtros `data_publicacao_inicio` / `data_publicacao_fim` agora levantam `TypeError` em vez de serem silenciosamente descartados. O backend Solr expoe um unico intervalo de datas (`dataIni`/`dataFim`, mapeado para `dt_juntada`), exposto canonicamente via `data_julgamento_*`. `InputCJSGTJES`/`InputCJPGTJES` deixam de herdar `DataPublicacaoMixin`, e os parametros `data_publicacao_*` saem da assinatura publica de `cjsg`/`cjsg_download`. Refs #165, #173.
- `DatajudScraper.listar_processos`: schema pydantic `InputListarProcessosDataJud` wired no metodo publico — kwargs desconhecidos passam a levantar `TypeError` com mensagem `DatajudScraper.listar_processos() got unexpected keyword argument(s): '<nome>'` em vez do `TypeError` nativo do Python (mais opaco), e filtros com formato invalido viram `ValidationError`. `paginas` aceita as 4 formas do contrato unico (`int | list[int] | range | None`), alinhado com `SearchBase`; lista esparsa (`paginas=[3, 5]`) vira `range(min, max+1)` antes da iteracao porque o cursor `search_after` da API e forwards-only — o usuario recebe o DataFrame contiguo das paginas 3, 4 e 5. `tamanho_pagina` sobe de `1000` para `5000` por default (validacao `Field(ge=10, le=10000)`); testes empiricos contra `api-publica.datajud.cnj.jus.br` mostraram que `size=5000` e ~2.5x mais rapido que 1000 com margem confortavel sob o timeout do gateway, enquanto `size=10000` (cap documentado da API) estoura `HTTP 504` intermitentemente. `call_datajud_api` ganha fallback automatico: ao receber `HTTP 504` ou `requests.Timeout`, refaz a requisicao **uma unica vez** com `size // 4` (minimo 100), mutando `query_payload["size"]` em place e emitindo `UserWarning`; o size reduzido fica sticky para paginas subsequentes do mesmo alias para nao pagar ~60s por pagina em gateway saturado consistente. Outros 5xx (500/502/503) nao acionam fallback. `paginas` promovido para `juscraper.schemas.PaginasMixin` (compartilhado com `SearchBase`); agregadores sem `pesquisa` compoem o mixin direto. `build_listar_processos_payload` extraido de `client.py:_listar_processos_por_alias` para `download.py` e reusado pelo capture script — single source of truth para o body Elasticsearch (regra 12 do CLAUDE.md), eliminando o drift documentado em #140. Refs #93, #118, #140, #152, #153.
- `cjpg`/`cjsg` da familia eSAJ (cjsg em TJSP/TJAC/TJAL/TJAM/TJCE/TJMS, cjpg em TJSP) agora dividem internamente intervalos `data_julgamento_*` que excedem 366 dias, baixam cada janela e concatenam o resultado deduplicando por `cd_acordao` (cjsg) ou `id_processo` (cjpg). Falhas em janelas individuais viram `UserWarning` e o DataFrame retorna parcial. Controlado pelo novo flag `auto_chunk: bool = True` (mixin `juscraper.schemas.AutoChunkMixin`); para o comportamento antigo (`ValueError` em janelas longas), passe `auto_chunk=False`. `auto_chunk=True` combinado com `paginas` em intervalo > 366 dias e `ValueError` por ambiguidade. Conflito `pesquisa` + alias deprecado (`query`/`termo`) tambem levanta `ValueError` no caminho chunked (paridade com o caminho noop). Orquestracao consolidada em `juscraper.courts._esaj.base.run_auto_chunk` — antes a logica vivia duplicada (~50 linhas) em `EsajSearchScraper.cjsg` e `TJSPScraper.cjpg`. Refs #130.
- Familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`) consolidada numa classe compartilhada `juscraper.courts._esaj.EsajSearchScraper`. Os 5 eSAJ-puros viraram clients de ~15 linhas cada (definem so `BASE_URL` e `TRIBUNAL_NAME`); TJCE adicionalmente sobrescreve o hook `_configure_session` para montar o TLS adapter `SECLEVEL=1`; TJSP sobrescreve `_build_cjsg_body` (body diferente), liga o hook de `conversationId` + UA Chrome, e mantem cjpg/cpopg/cposg nos proprios modulos. `QueryTooLongError` do TJSP migrada para `juscraper.courts.tjsp.exceptions`. Saldo: ~2500 linhas removidas em `src/juscraper/courts/`. **Dependencia nova: `pydantic>=2.0.0`.** API publica preservada byte-a-byte; todos os contratos pre-existentes passam sem alteracao. POC do #84 aplicada a familia 1A. Refs #84, #93, #104.
- O formato de data esperado pelo backend foi movido do parametro `date_format` de `apply_input_pipeline_search` para um `ClassVar[str]` no schema (`BACKEND_DATE_FORMAT`, default `"%d/%m/%Y"` para eSAJ). Os 5 schemas 1C-a declaram `BACKEND_DATE_FORMAT = "%Y-%m-%d"`. O parametro `date_format` saiu da assinatura publica do helper — a info passa a viver junto com o schema, onde logicamente pertence. Refs #84, #93.
- TJPA `cjsg` agora roda o pipeline pydantic com `method_name="TJPAScraper.cjsg()"` (antes delegava ao `cjsg_download` e a mensagem de erro mostrava o nome interno). Refs #84, #93.
- `juscraper.utils.params.resolve_deprecated_alias` agora checa colisao **antes** de emitir o `DeprecationWarning`. Quando o caller passa canonical e alias simultaneamente, levanta `ValueError` direto sem warning intermediario.
- `juscraper.utils.params.validate_intervalo_datas` aceita `max_dias=None` (desabilita checagem de janela mantendo formato e ordem `inicio <= fim`) e parametro `origem_mensagem` (default fallback `"O backend"`; eSAJ passa `"O eSAJ"` explicitamente). Janela default eSAJ aumentada de 365 para 366 dias para nao rejeitar cliente-side uma janela de 1 ano calendario que atravesse 29/02. Refs #128.
- **BREAKING (colunas de saida padronizadas):** DataFrames de `cjsg` dos tribunais TJES, TJMT, TJRS, TJRN, TJPE e TJRO passam a usar nomes canonicos uniformes para colunas semanticamente equivalentes. Renomeacoes: `nr_processo`/`numero_unico` -> `processo` (TJES, TJMT); `classe_cnj`/`classe_judicial` -> `classe` (TJRS, TJRN, TJES, TJPE, TJRO); `assunto_cnj`/`assunto_principal` -> `assunto` (TJRS, TJPE, TJES); `magistrado` -> `relator` (TJES). Codigo que acessa colunas pelo nome antigo (ex.: `df["classe_cnj"]`) precisa ser atualizado. Refs #93, #117.
- `OutputCJSGBase.ementa` relaxado para `Optional[str]` (TJGO entrega o texto completo em `texto`, nao em `ementa`); `OutputCJSGBase.data_julgamento` aceita agora `date | str | None` para refletir os parsers que ja convertem para `datetime.date`. `OutputCJSGEsaj` (compartilhado por TJAC/TJAL/TJAM/TJCE/TJMS/TJSP) declara explicitamente `relatora: str | None = None` para refletir o que o parser eSAJ hoje emite — TODO no docstring aponta o PR dedicado que deve normalizar `relatora -> relator`. Refs #93, #117.
- **BREAKING:** DataJud `listar_processos` agora levanta `ValueError` em vez de retornar DataFrame vazio quando a sigla do tribunal nao existe nos mappings ou quando nem `tribunal` nem `numero_processo` sao fornecidos. Erros de input do chamador deixam de falhar silenciosamente. Refs #57.
- Sdist (`juscraper-X.Y.Z.tar.gz` no PyPI) passa a incluir somente `src/juscraper/`, README, LICENSE, CHANGELOG, CONTRIBUTING, CONDUCT e `pyproject.toml`. Diretorios `tests/`, `docs/`, `issues/`, `scripts/`, `.claude/`, `.github/` e caches deixam de ser empacotados — sem a configuracao explicita o tarball cresceria proporcionalmente a `tests/<tribunal>/samples/` (~25 MB hoje). Wheel ja excluia `tests/` por default do hatchling com layout `src/`; agora a configuracao esta explicita via `[tool.hatch.build.targets.wheel] packages = ["src/juscraper"]`. Adicionado guard no workflow `publish.yml` que falha o build se o wheel/sdist contiver `tests/` ou se o sdist exceder 1 MB. Refs #139.
- Dev-tooling: `pyproject.toml` agora inclui `types-requests` e `pytest-mock` nas dev extras e `filterwarnings = ["error"]` na config do pytest. `pytest` por default executa apenas testes offline via `addopts = -m 'not integration'`; integracao via `pytest -m integration`; tudo via `pytest -m ""`. Adicionado `responses` em dev deps; novo marker `vcr` para `pytest-recording`. Criados `tests/conftest.py` (fixture `tests_dir`) e `tests/_helpers.py` (`load_sample`, `load_sample_bytes`). Refs #19, #84, #101.

### Deprecated

- Parametros de Input renomeados para canonicos; os nomes antigos continuam aceitos com `DeprecationWarning` por um ciclo:
  - `nr_processo` -> `numero_processo` em TJPB, TJRN, TJRO.
  - `numero_cnj` -> `numero_processo` em TJAP.
  - `magistrado` -> `relator`, `classe_judicial` -> `classe` em TJES (`cjsg` e `cjpg`).
  - `classe_cnj` -> `classe`, `assunto_cnj` -> `assunto` em TJPE.

  Helpers `juscraper.utils.params.pop_deprecated_alias` (pop + warning) e `juscraper.utils.params.resolve_deprecated_alias` (pop + checagem de colisao + reatribuicao) centralizam o padrao. Refs #93, #117.

### Removed

- `MANIFEST.in` na raiz. Era vestigio do tempo do setuptools; o backend de build atual (hatchling) ignora completamente. Politica de empacotamento agora vive em `[tool.hatch.build.targets.*]` no `pyproject.toml`. Refs #139.
- Shim `src/juscraper/courts/tjsp/cjsg_download.py` (compatibility bridge para testes legados que importavam `cjsg_download`/`QueryTooLongError`). Imports devem passar a usar `juscraper.courts.tjsp.exceptions`. A docstring de `juscraper.courts.tjsp.forms.build_tjsp_cjsg_body` foi reescrita para documentar as diferencas funcionais reais do body do TJSP vs. eSAJ-puros (sem `conversationId`, sem `dtPublicacao*`, `baixar_sg` mapeia para `origem`).

### Fixed

- Documentacao da familia eSAJ — docstrings de `cjsg`/`cjpg` agora listam todos os filtros aceitos via `**kwargs` (com tipo, default, hint do backend e referencia ao schema pydantic). Antes a docstring tinha apenas uma linha e `help(tjsp.cjpg)` nao revelava `varas`/`classes`/`assuntos`/`id_processo`/`data_julgamento_*`, dando a impressao de que esses filtros nao existiam. Sem mudanca de runtime — os filtros ja eram aceitos via `**kwargs` e validados pelo pydantic. Afeta `EsajSearchScraper.cjsg`/`cjsg_download` em `_esaj/base.py` (TJAC/TJAL/TJAM/TJCE/TJMS por heranca) e `TJSPScraper.cjsg`/`cjsg_download`/`cjpg`/`cjpg_download`. Notebook `docs/notebooks/tjsp.ipynb` atualizado para usar `data_julgamento_inicio`/`fim` canonicos. Fecha #66.
- TJPR `cjsg`: propagava `**kwargs` com aliases deprecados (`query`, `termo`, `data_inicio`, `data_fim`) para `cjsg_download`, fazendo `normalize_pesquisa` levantar `ValueError` na segunda invocacao. Agora pop dos aliases via `pop_normalize_aliases` antes do re-pass.
- TJBA CJSG: `_to_iso` aceita datas em formato brasileiro (DD/MM/YYYY) alem de ISO, usando `to_iso_date`. Antes produzia strings invalidas como `"12/03/2025T03:00:00.000Z"` quando o usuario passava no formato canonico do projeto.
- TJDFT CJSG: filtro de datas de julgamento e publicacao agora e enviado ao backend via `termosAcessorios` (formato `"entre YYYY-MM-DD e YYYY-MM-DD"`). Antes o scraper emitia um `UserWarning` dizendo que os parametros nao eram suportados e devolvia resultados sem filtro.
- TJTO CJSG: `tempo_julgados` passa a ser enviado como `"pers"` quando `data_julgamento_inicio`/`fim` sao fornecidos. Sem isso o backend ignorava silenciosamente `dat_jul_ini`/`dat_jul_fim` e devolvia os julgamentos mais recentes.
- TJRN CJSG: filtro de datas e coluna `data_julgamento` consertados. O backend espera `dt_inicio`/`dt_fim` no formato `DD-MM-YYYY` (tracos, nao barras). O parser passa a ler `dt_assinatura_teor` como `data_julgamento` (o campo `dt_julgamento` que o codigo esperava nao existe no indice Elasticsearch) e expoe `data_publicacao` a partir de `dt_publicacao`.
- TJPI CJSG: filtro de datas (`data_min`/`data_max`) agora e enviado na query string da busca HTML. Antes o scraper ignorava `data_julgamento_inicio`/`fim` e devolvia resultados de qualquer data.
- TJMT CJSG: `filtro.periodoDataDe`/`filtro.periodoDataAte` agora sao enviados em ISO-8601 (`YYYY-MM-DD`). O backend Hellsgate ignorava silenciosamente qualquer outro formato.
- TJPA CJSG: `dataJulgamentoInicio`/`dataJulgamentoFim` e `dataPublicacaoInicio`/`dataPublicacaoFim` agora sao serializados em ISO. O backend Elasticsearch retornava HTTP 400 com DD/MM/YYYY.
- TJRO CJSG: `dtjulgamento_inicio`/`dtjulgamento_fim` agora sao serializados em ISO. O backend retornava HTTP 500 com DD/MM/YYYY.
- TJPB CJSG: filtro de datas agora bate com o que o usuario pede. O client passa a pos-filtrar o DataFrame retornado para manter so as linhas cujo `dt_ementa` (exposto como `data_julgamento`) esta no intervalo `data_julgamento_inicio`/`fim`. Antes, rows podiam vir com `dt_ementa` completamente fora da janela solicitada.
- TJRR CJSG: descoberta dinamica dos nomes dos campos JSF e snapshot completo dos defaults do formulario. Os IDs auto-gerados pelo JSF mudam quando o tribunal adiciona/reordena componentes; o scraper ficou silenciosamente retornando zero resultados depois da ultima renumeracao. `_get_form_fields` agora resolve o input via `id=consultaAtual` e o submit pelo primeiro `<button>` `menuinicial:j_idt…` que nao comeca com `menuinicial:btn_`. `_collect_form_defaults` copia todo input do form. Envia tambem `Origin`/`Referer`.
- TJRS `cjsg`: corrigida a primeira pagina da busca. O scraper enviava `pagina_atual=0`; o backend interpreta isso como `start=-10` e retorna erro Solr. Agora `paginas=1` envia `pagina_atual=1`. Aliases deprecados agora sao efetivamente descartados de `kwargs` apos `normalize_pesquisa`/`normalize_datas` (antes o `DeprecationWarning` era engolido por um `TypeError: got multiple values for keyword argument`).
- TJMT/TJBA `cjsg_parse`: respostas sem resultados podem vir do backend real com `null` em qualquer nivel intermediario (`AcordaoCollection`, `data.filter.decisoes`); os parsers agora tratam `null` como lista vazia / dict ausente e retornam DataFrame vazio em vez de quebrar.
- eSAJ `cjsg_n_pags` (compartilhado em `juscraper.courts._esaj.parse`): restaurada a deteccao de captcha/erro que existia no parser TJSP antes da consolidacao do PR #115. Paginas que retornam divs com classe contendo `error`/`erro`/`mensagem erro` agora levantam `ValueError("Captcha nao foi resolvido...")` ou `ValueError("Erro detectado na pagina: ...")` em vez do confuso `"Nao foi possivel encontrar o seletor de numero de paginas"`. Vale para os 6 tribunais eSAJ.
- eSAJ `cjsg_download` e TJSP `cjpg_download`/`cjsg_download`: aliases deprecados `query`/`termo` agora sao de fato popados de `kwargs` com `DeprecationWarning` antes da validacao pydantic — a docstring prometia isso mas `normalize_pesquisa` nunca era chamado, entao o usuario recebia `TypeError` em vez do warning documentado. Refs #68, #93.
- eSAJ (TJSP cjpg/cjsg, TJAC/TJCE/TJMS/TJAM cjsg): validacao antecipada do intervalo entre `data_*_inicio` e `data_*_fim`. O eSAJ rejeita janelas maiores que 1 ano, mas antes o erro aparecia como "Nao foi possivel encontrar o seletor de numero de paginas" apos a requisicao ser feita. Agora um `ValueError` acionavel e lancado antes de qualquer HTTP, via novo helper `juscraper.utils.params.validate_intervalo_datas`. Refs #91.
- eSAJ (TJSP, TJAL, TJAM, TJAC, TJMS, TJCE): scrapers de CJSG agora validam o certificado SSL dos servidores (`session.verify = True`, default do `requests`). O `verify=False` era heranca do port do script R sem justificativa tecnica. No TJCE, `_TJCETLSAdapter` reduzido a apenas `set_ciphers("DEFAULT:@SECLEVEL=1")`.
- `juscraper.utils.cnj.clean_cnj`: agora remove qualquer caractere nao-digito (espacos, tabs, quebras de linha). Numeros CNJ vindos de CSV/Excel com whitespace deixam de ser silenciosamente descartados pelo DataJud. Refs #59.
- DataJud: ao buscar por `numero_processo`, a query Elasticsearch agora envia o CNJ ja limpo (apenas digitos) em vez do original com pontos e tracos. Antes, numeros formatados retornavam zero hits silenciosamente. Refs #60.
- DataJud: completados os mapeamentos de TRTs (24) e TREs (27), incluindo TST e TSE, em `ID_JUSTICA_TRIBUNAL_TO_ALIAS` e `TRIBUNAL_TO_ALIAS`. Antes, processos das Justicas do Trabalho e Eleitoral consultados via `numero_processo` eram descartados silenciosamente. Refs #56.
- DataJud: problemas de runtime (CNJ invalido, tribunal nao mapeado, falha de API, timeout, JSON corrompido) agora emitem `warnings.warn(UserWarning)` alem do `logger.error/warning`. Em uso tipico via Jupyter Notebook, sem handler de logging configurado, esses problemas eram completamente invisiveis. `UserWarning` e visivel por padrao em notebooks. Removido warning redundante "Nenhum CNJ válido foi reconhecido" quando todos os CNJs informados ja emitiram warning individual. Refs #57.
- TJSP `cposg_download`: condicao `elif self.method == 'json'` era dead code — `set_method` so aceita `'html'` ou `'api'`, entao o caminho da API nunca era executado. Agora compara contra `'api'` corretamente.
- TJSP `get_cpopg_download_links`: ramo `else` nunca populava a lista de links retornada (atribuia `processos = lista.find_all('a')` e descartava o resultado). Agora itera sobre os `<a href>` e acrescenta cada href em `links`.
- TJSP `cpopg_download`/`cposg_download`: `RuntimeError` introduzido ao trocar `dict.get(k, [None])[0]` por early-raise (PR #105) escapava dos `except` de batch e abortava o download de todos os CNJs seguintes quando um link de listagem vinha sem `processo.codigo`. Agora `RuntimeError` e capturado no loop externo e o batch segue para o proximo CNJ. `cposg_download_html` tambem levanta `RuntimeError` explicito quando nenhum processo e baixado, em vez de quebrar com `IndexError` em `paths[0]`.
- TJSP CJPG: `cjpg_n_pags` agora retorna `0` quando a busca nao gera resultados (HTML de formulario com "Nao foi encontrado nenhum resultado"), em vez de levantar `ValueError`. `cjpg_download` faz early-return salvando apenas a primeira pagina, e `.cjpg(...)` devolve DataFrame vazio. Mesmo padrao ja usado em `cjsg_n_pags`/`cjsg_download`. Refs #109.
- TJSP `cjpg_download` (modulo interno): removida chamada duplicada de `validate_pesquisa_length` que rodava tanto em `client.py` quanto no helper interno. A validacao agora acontece exclusivamente no ponto de entrada publico.

### Known Issues

- Dois tribunais tem o teste de filtro de datas marcado como `xfail` estrito (lista `KNOWN_FILTRO_FAILURES` em `test_release_date_filter.py`): tjap (Tucujuris genuinamente nao expoe filtro por data — confirmado na engenharia reversa do HTML, JS e API do site) e tjrj (endpoint legado ASP.NET devolve HTTP 500 ate sem filtros). Ambas sao server-side — nao dependem do cliente. Cada fix deve remover o tribunal da lista — `strict=True` sinaliza quando o bug se resolve sozinho.

## [0.2.1] - 2026-04-13

### Fixed

- TJSP CJPG: extracao do numero de paginas voltou a funcionar apos mudanca no HTML do tribunal. O texto da paginacao mudou de "Mostrando 1 a 10 de N resultados" para "Resultados 1 a 10 de N", e o regex antigo exigia a palavra "resultado" depois do numero. `cjpg_n_pags` agora usa estrategia robusta de seletor + regex em cascata (mesmo padrao de `cjsg_n_pags`), suportando ambos os formatos.

### Added

- TJRJ: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Rio de Janeiro, via API JSON. O site exibe reCAPTCHA v2 mas o backend nao valida o token. Filtros: pesquisa livre, data de julgamento
- TJGO: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Goias (Projudi). O site exibe Cloudflare Turnstile mas o backend nao valida o token. Filtros: instancia, area, serventia, data de publicacao, numero do processo
- TJMG: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Minas Gerais. Captcha numerico de 5 digitos resolvido automaticamente via txtcaptcha. Filtros: pesquisa por ementa ou inteiro teor, datas de julgamento e publicacao, ordenacao
- TJSE: documentado como nao suportado (Cloudflare Turnstile com validacao server-side)
- TJMA: documentado como nao suportado (Google reCAPTCHA v2 invisible com validacao server-side)
- TJAC: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Acre, baseado na plataforma eSAJ. Filtros: pesquisa livre, ementa, classe, assunto, orgao julgador, comarca, datas de julgamento e publicacao, origem e tipo de decisao
- TJAL: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Alagoas, baseado na plataforma eSAJ. Filtros: pesquisa livre, ementa, classe, assunto, orgao julgador, comarca, datas de julgamento e publicacao, origem e tipo de decisao
- TJAM: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Amazonas, baseado na plataforma eSAJ. Filtros: pesquisa livre, ementa, classe, assunto, orgao julgador, comarca, datas de julgamento e publicacao, origem e tipo de decisao
- TJMS: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Mato Grosso do Sul, baseado na plataforma eSAJ. Filtros: pesquisa livre, ementa, classe, assunto, orgao julgador, comarca, datas de julgamento e publicacao, origem e tipo de decisao

## [0.2.0] - 2026-04-09

### Added

- TJPB: scraper de jurisprudencia (cjsg) do Tribunal de Justica da Paraiba, via API JSON (plataforma PJe/TJRN). Filtros: classe judicial, orgao julgador, relator, datas, origem, decisoes monocraticas
- TJPI: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Piaui, via parsing HTML do JusPI. Filtros: tipo de decisao (acordao, decisao terminativa, sumula), relator, classe, orgao julgador
- TJRN: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Rio Grande do Norte, via API Elasticsearch. Filtros: classe judicial, orgao julgador, relator, colegiado, sistema (PJE/SAJ), tipo de decisao, jurisdicao, grau, datas
- TJRO: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Rondonia, via API Elasticsearch (JURIS). Filtros: tipo de documento, magistrado, orgao julgador, classe judicial, instancia, datas de julgamento, termo exato
- TJRR: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Roraima, via JSF/PrimeFaces com ViewState. Filtros: relator, orgao julgador, especie de recurso, datas
- TJSC: scraper de jurisprudencia (cjsg) do Tribunal de Justica de Santa Catarina, via eproc PHP. Filtros: campo de busca (ementa/inteiro teor), processo, datas de decisao e publicacao
- TJAP: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Amapa, via API REST do Tucujuris. Filtros disponiveis: orgao julgador, relator, secretaria, classe, origem, votacao, numero CNJ, numero do acordao, palavras exatas
- TJTO: scraper de jurisprudencia do Tribunal de Justica do Tocantins
  - `cjsg`: jurisprudencia de 2o grau (acordaos, decisoes monocraticas, sentencas)
  - `cjpg`: jurisprudencia de 1o grau (acordaos, decisoes monocraticas, sentencas)
  - Filtros: pesquisa livre, datas de julgamento, numero do processo, ordenacao, restricao a ementa
- TJPA: scraper de jurisprudencia (cjsg) do Tribunal de Justica do Estado do Para, com suporte a filtros por relator, orgao julgador colegiado, classe, assunto, datas de julgamento e publicacao
- Adicionado scraper de jurisprudência (CJSG) para o TJCE (Tribunal de Justiça do Ceará), baseado na plataforma eSAJ
- Suporte a filtros: pesquisa livre, ementa, classe, assunto, órgão julgador, datas de julgamento e publicação, origem e tipo de decisão
- Adaptação TLS para o servidor do TJCE que requer SECLEVEL=1
- TJPE: implementado scraper de jurisprudência (`cjsg`) para o Tribunal de Justiça de Pernambuco, com suporte a pesquisa livre, filtros de data de julgamento, relator, classe CNJ, assunto CNJ e paginação
- Scraper para o TJBA (Tribunal de Justica do Estado da Bahia) com consulta de jurisprudencia (cjsg) via API GraphQL
- Filtros disponiveis: pesquisa textual, numero do recurso, orgao julgador, relator, classe, data de publicacao, instancia (2o grau / turmas recursais), tipo de decisao (acordaos / monocraticas)
- Notebook de exemplo e documentacao do TJBA
- Scraper para o TJMT (Tribunal de Justica do Estado de Mato Grosso) com suporte a consulta de jurisprudencia (`cjsg`) para acordaos e decisoes monocraticas
- Filtros disponiveis: pesquisa livre, datas de julgamento, relator, orgao julgador, classe, tipo de processo e thesaurus
- Notebook de exemplo e documentacao para o TJMT
- Novo scraper para o TJES (Tribunal de Justica do Espirito Santo)
  - `cjsg`: jurisprudencia de 2o grau (cores: `pje2g`, `pje2g_mono`, `legado`, `turma_recursal_legado`)
  - `cjpg`: jurisprudencia de 1o grau (core: `pje1g`)
  - Filtros: magistrado, orgao julgador, classe judicial, jurisdicao, assunto, datas, busca exata, ordenacao

## [0.1.7] - 2026-03-31

### Fixed

- CPOPG (TJSP): corrigido `id_processo` e `classe` retornando `None` em processos do tipo incidente (ex: Cumprimento de Sentença), que usam template HTML alternativo sem `id="numeroProcesso"` e `id="classeProcesso"`
- CPOPG (TJSP): adicionada extração de campos extras dos dados básicos que antes eram ignorados: `processo_principal`, `controle`, `area`, `outros_assuntos`, entre outros

## [0.1.6] - 2026-03-31

### Added

- Adicionado `CLAUDE.md` com convencoes do projeto para orientar agentes de IA
- Adicionado módulo `juscraper.utils.params` com funções de normalização de parâmetros
- Auto-paginação: `paginas` agora aceita `int | list | range | None` em todos os scrapers; default `None` baixa todas as páginas disponíveis

### Changed

- **BREAKING:** Padronizados nomes dos parâmetros da API pública (#63):
  - Busca: todos os scrapers usam `pesquisa` (antes `query`/`termo` em TJDFT/TJPR/TJRS)
  - Datas: sufixo `_de/_ate` renomeado para `_inicio/_fim` em TJPR/TJRS; TJSP `data_inicio/fim` renomeado para `data_julgamento_inicio/fim`
- **BREAKING:** Padronizado parâmetro `paginas` como 1-based em todos os scrapers: `range(1, 4)` baixa páginas 1, 2 e 3. Usuários que passavam `range(0, N)` devem atualizar para `range(1, N+1)`
- Removidas dependências não utilizadas: `pyppeteer`, `playwright`, `selenium`, `webdriver-manager` (#25)
- Removida constraint de `websockets` que era necessária apenas por causa do pyppeteer
- Ajustado constraint de `pandas` para `>=2.0.0,<3.0.0` para compatibilidade com Google Colab (#25)
- Adicionado `uv.lock` ao `.gitignore` (lockfile não deve ser versionado em bibliotecas)

### Deprecated

- Nomes antigos de parâmetros (`query`, `termo`, `data_*_de/_ate`, `data_inicio/fim`) ainda aceitos com `DeprecationWarning`; serão removidos em v1.0

### Fixed

- CJPG (TJSP): primeira página (r0) agora é salva corretamente — antes era perdida devido a offset duplo no loop
- CJSG (TJSP): paginação corrigida de 0-based para 1-based
- TJRS: corrigida inconsistência na conversão de paginação (range era convertido incorretamente)
- TJDFT: corrigido default `paginas=0` que resultava em range vazio (agora `paginas=1`)
- Filtro `ano_ajuizamento` no Datajud agora aceita ambos os formatos de data (ISO `2020-01-01` e compacto `20200101103323`), corrigindo perda silenciosa de até 100% dos processos em TRF1, TRF3, TRF4 e TRF5 (#51)
- Adicionado `track_total_hits: true` nas queries do Datajud para retornar contagem total exata em vez de truncar em 10.000
- Adicionado log com total de processos encontrados na primeira página para visibilidade

## [0.1.5] - 2025-12-28

### Changed

- Refatoração completa do módulo CJSG (TJSP) para usar apenas `requests` em vez de Playwright
- Removida dependência de automação de navegador para downloads do CJSG, seguindo a mesma abordagem do script R de referência
- Melhorada a documentação do notebook TJSP com explicações detalhadas sobre todas as funções

### Fixed

- Correção do encoding: arquivos HTML agora são salvos e lidos corretamente em latin1, preservando caracteres especiais
- Correção da barra de progresso para incluir a primeira página na contagem total
- Correção dos nomes de colunas: `argapso_julgador` → `orgao_julgador` e `data_publicaassapso` → `data_publicacao`
- Melhorada a extração do número de páginas seguindo a mesma lógica do código R de referência
- Removido parâmetro `headless` que não é mais necessário após remoção do Playwright

## [0.1.4] - 2025-01-XX

### Fixed

- Correção na extração de movimentações e descrições no parser do CPOSG (TJSP)
- Movimentações agora são extraídas corretamente da tabela HTML, incluindo movimento e descrição

## [0.1.3] - 2025-07-19

### Added

- Binário e texto dos documentos no Jusbr

### Changed

-

## [0.1.0] - 2025-07-19

### Added

- Modularização do TJSP
- Tribunais adicionados: TJRS, TJPR, TJDFT (apenas CJSG)
- Agregadores adicionados: Datajud, Jusbr
- Configuração completa para publicação no PyPI
- Workflows do GitHub Actions para CI/CD
- Configuração de ferramentas de qualidade de código (black, isort, flake8, mypy)
- Pre-commit hooks
- Script automatizado de release

### Changed

- Reorganização das dependências em grupos opcionais
- Melhoria na estrutura do projeto

## [0.0.1] - 2024-12-17

### Added

- First release of `juscraper`!
