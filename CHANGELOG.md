# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `TJSPScraper.cjsg` aceita `pesquisa=""` por default — antes o argumento era obrigatorio e `tjsp.cjsg(classe="...", assunto="...")` levantava `TypeError`. Agora o usuario pode buscar so por filtros (sem termo textual), igualando o comportamento de `cjpg`. Refs #229.

## [0.3.0] - 2026-05-03

### Added

<<<<<<< feat/trf3-trf5-pje-cpopg
- Raspador TRF1 (`cpopg` — consulta pública de processos de 1º grau via PJe em `pje1g-consultapublica.trf1.jus.br/consultapublica/`). Mesma assinatura, schema (`InputCpopgTRF1`/`OutputCpopgTRF1`) e shape de retorno dos raspadores TRF3/TRF5; o form layout do TRF1 segue o mesmo padrão do TRF3 (autocomplete `classeJudicial` + bloco `dataAutuacaoDecoration`), então a divergência fica concentrada em `BASE_URL`. Implementação completamente independente em `courts/trf1/` (`client.py`, `download.py`, `parse.py`, `schemas.py`), seguindo a mesma decisão arquitetural do par TRF3/TRF5: tribunais podem trocar de sistema a qualquer momento e acoplar PJe-do-TRF1 a uma base compartilhada com PJe-do-TRF3 forçaria refator em cascata. Samples HTML versionados em `tests/trf1/samples/cpopg/`; cobertura: contrato offline + unit tests da paginação + integração (`@pytest.mark.integration`).
- Raspadores TRF3 e TRF5 (`cpopg` — consulta pública de processos de 1º grau via PJe). Acessam a `ConsultaPublica/listView.seam` em `pje1g.trf3.jus.br/pje/` e `pje1g.trf5.jus.br/pjeconsulta/`, fazendo o fluxo de 3 passos (GET form → POST search → GET detail com token `ca`) e devolvendo um `pd.DataFrame` com uma linha por processo (colunas: `id_cnj`, `processo`, `classe`, `assunto`, `data_distribuicao`, `orgao_julgador`, `jurisdicao`, `endereco_orgao`, `polo_ativo`, `polo_passivo`, `movimentacoes`, `documentos`). Aceita um CNJ ou lista de CNJs; processos sem hit no portal público devolvem linha com apenas `id_cnj`. Cada tribunal tem implementação **completamente independente** em `courts/trf3/` e `courts/trf5/` (`client.py`, `download.py`, `parse.py`, `schemas.py`) — nenhuma base ou helper compartilhado, mesmo que ambos usem PJe hoje. Optou-se conscientemente pela duplicação porque tribunais podem trocar de sistema a qualquer momento e acoplamento via base compartilhada forçaria refator em cascata. Cada `download.py` extrai dinamicamente os IDs JSF auto-gerados (`j_idNNN`) do form HTML do próprio tribunal, então um redeploy do PJe não quebra o scraper. Especializações por tribunal: TRF3 envia `classeJudicial`+`sgbClasseJudicial_selection` (autocomplete) e os campos `dataAutuacaoDecoration` no payload, e ultrapassa o filtro Akamai (`ak_bmsc`) com header set browser-like; TRF5 envia `classeProcessualProcessoHidden` (popup picker) e omite as datas, e ignora o reCAPTCHA renderizado no form (dead code: `if (false)` no `executarReCaptcha`). Schemas pydantic em `courts/{trf3,trf5}/schemas.py` com `extra='forbid'` no Input. Samples HTML em `tests/{trf3,trf5}/samples/cpopg/` capturados via `tests/fixtures/capture/{trf3,trf5}.py`. Cobertura de testes: contrato offline (sub-set matcher de form-encoded payload), schema, integração (`@pytest.mark.integration`).
- Agregador `comunica_cnj` (`ComunicaCNJScraper`) para a API publica de Comunicacoes Processuais do CNJ (`https://comunicaapi.pje.jus.br/api/v1/comunicacao`). Metodo publico `listar_comunicacoes(pesquisa, paginas=None, data_disponibilizacao_inicio=None, data_disponibilizacao_fim=None, itens_por_pagina=100)` devolve `pandas.DataFrame` com uma linha por comunicacao. Validacao via schema pydantic `InputListarComunicacoesComunicaCNJ` (`extra="forbid"`); kwargs desconhecidos viram `TypeError`. `pesquisa` ausente vira `ValidationError`. Output schema `OutputListarComunicacoesComunicaCNJ` (`extra="allow"`, pivot `numero_processo`) registrado em `tests/schemas/test_output_parity.py`. Datas aceitam tanto ISO `YYYY-MM-DD` quanto formato brasileiro `DD/MM/YYYY` (convertido via `to_iso_date`); intervalo invalido vira `ValueError` via `validate_intervalo_datas`. Os nomes `data_disponibilizacao_inicio`/`_fim` foram escolhidos canonicos exatamente para evitar colisao com `data_inicio`/`data_fim` (alias deprecado de `data_julgamento_*` em `DEPRECATED_ALIASES`/`DATE_ALIASES`). Default `sleep_time=0.5` entre paginas, alinhado com `DatajudScraper`, para nao agredir a API publica do CNJ em batches grandes. Suite de contratos offline em `tests/comunica_cnj/test_listar_comunicacoes_contract.py` + `test_listar_comunicacoes_filters_contract.py` com 12 cenarios cobrindo multi-pagina, single page, no_results, propagacao de filtros e validacoes; o caso `comunica_cnj.listar_comunicacoes` esta registrado em `tests/schemas/test_docstring_parity.py::CASES`, fechando a paridade docstring/schema. Samples reais capturados via `python -m tests.fixtures.capture.comunica_cnj`. Modulo herdado do `bdcdo/raspe`, com correcao para a chave de resposta da API que mudou de `itens` (PT) para `items` (EN).
- `DatajudScraper.listar_processos` ganha filtros novos para expor recursos da API Elasticsearch do CNJ que antes nao eram acessiveis pela interface publica (refs #49): `data_ajuizamento_inicio`/`data_ajuizamento_fim` (range em `dataAjuizamento` com padrao dual-format ISO + compacto, mesmo da #51, mutuamente exclusivo com `ano_ajuizamento`); `tipos_movimentacao` (lista de nomes amigaveis — `decisao`/`sentenca`/`julgamento`/`tutela`/`transito_julgado` — resolvidos via novo mapping `TIPOS_MOVIMENTACAO` em `juscraper.aggregators.datajud.mappings`); `movimentos_codigo` (lista de codigos TPU diretos, concatenada com `tipos_movimentacao` quando ambos sao passados); `orgao_julgador` (`match` em `orgaoJulgador.nome`); `query` (override total da query Elasticsearch — passa um `dict` que vira a chave `query` do payload literalmente, mutuamente exclusivo com todos os filtros amigaveis acima e exigindo `tribunal` explicito; em troca, oferece paridade com requisicao direta a `/<alias>/_search` para `must_not`/`should`/`range` em campos arbitrarios/`wildcard`/`nested`/etc.). `data_inicio`/`data_fim` (alias generico do projeto que mapeia para `data_julgamento_*` em scrapers de jurisprudencia) **nao** e aceito aqui — o DataJud filtra por ajuizamento, nao julgamento, e o nome canonico explicito `data_ajuizamento_*` torna a semantica obvia. `extra="forbid"` faz quem usar o nome generico receber `TypeError` direto.
- `DatajudScraper.contar_processos` ganha paridade com `listar_processos` no escopo de #176: `data_ajuizamento_inicio`/`_fim`, `tipos_movimentacao`, `movimentos_codigo`, `orgao_julgador` e o escape-hatch `query` agora sao aceitos tambem na contagem. `InputContarProcessosDataJud` reusa os mesmos validators de `InputListarProcessosDataJud` (mutual exclusivity entre `ano_ajuizamento` e `data_ajuizamento_*`, formato ISO 8601, `query` exclusivo com filtros amigaveis e exigindo `tribunal`, `tipos_movimentacao` so aceita nomes mapeados); `build_contar_processos_payload` passa a delegar a montagem do `query` interno para o helper compartilhado `_build_query_amigavel`, garantindo que listar e contar produzam o mesmo body para os mesmos filtros.
- Schemas pydantic de Input e Output para **todos** os endpoints publicos implementados (nao stubs) nos 25 tribunais e 2 agregadores do juscraper. Tribunais ainda nao refatorados recebem schema-arquivo sem wiring — servem como documentacao executavel da API publica e ponto de encaixe para a refatoracao futura. Bases compartilhadas extraidas por evidencia concreta: `SearchBase` (25 ocorrencias de `pesquisa`/`paginas`), `DataJulgamentoMixin` (13 tribunais, agora incluindo TJPI apos #94/#125 e TJDFT apos #165), `DataPublicacaoMixin` (11, agora incluindo TJDFT apos #165), `CnjInputBase`/`OutputCnjConsultaBase` para endpoints de consulta processual, `OutputRelatoriaMixin` (>= 10 parsers cjsg) e `OutputDataPublicacaoMixin` (>= 9 parsers). Schemas wired no metodo publico via `extra="forbid"` em eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`/`cjpg`), familia 1C-a (TJRN/TJPA/TJRO/TJSC/TJPI `cjsg`), familia 1B parcial (TJDFT `cjsg`, TJES `cjsg`/`cjpg` — primeira leva de #165; TJBA/TJMT `cjsg` — segunda leva de #165; TJAP/TJRS `cjsg` — terceira leva de #165; TJPB `cjsg`, TJTO `cjsg`/`cjpg` — quarta leva de #165), TJPR `cjsg` (1C-c1 — quinta leva de #165), TJGO/TJRR/TJMG `cjsg` (sexta leva de #165) e DataJud `listar_processos` — kwargs desconhecidos viram `TypeError`/`ValidationError` em vez de serem silenciosamente ignorados. Refs #93, #117, #120, #125, #152, #165.
- Utilities publicas em `juscraper.utils.params`: `apply_input_pipeline_search(schema_cls, method_name, *, pesquisa, paginas, kwargs, max_dias=None, origem_mensagem=None, **canonical_filters)` (pipeline canonico de validacao em uma chamada — `normalize_paginas` -> `normalize_datas` -> `pop_normalize_aliases` -> `validate_intervalo_datas` -> schema -> `raise_on_extra_kwargs`); `raise_on_extra_kwargs` (converte `ValidationError` com `extra_forbidden` em `TypeError` amigavel, com sugestao de typo via `difflib.get_close_matches` quando o `schema_cls` e fornecido — ex.: `data_juglamento_inicio` -> `(você quis dizer 'data_julgamento_inicio'?)`); `pop_normalize_aliases` + constantes `SEARCH_ALIASES`/`DATE_ALIASES`/`DATE_CANONICAL`; `to_iso_date` (contraparte de `to_br_date` para backends ISO-8601); `pop_deprecated_alias` e `resolve_deprecated_alias` (centralizam pop + warning + checagem de colisao). O parametro chama-se `origem_mensagem` (nao `origem`) porque varios scrapers usam `origem` como filtro do backend. Refs #84, #93, #119, #128.
- TJSP CJPG/CJSG: validacao de tamanho do campo `pesquisa` antes da requisicao. O backend do eSAJ trunca strings com mais de 120 caracteres silenciosamente; agora `cjpg_download` e `cjsg_download` levantam `QueryTooLongError` (subclasse de `ValueError`, exportada em `juscraper.courts.tjsp.exceptions`) quando o limite e excedido. Refs #35.
- Suite de contratos offline expandida cobrindo `cjsg` (e `cjpg` quando aplicavel) em TJAC, TJAL, TJAM, TJCE, TJMS, TJSP, TJDFT, TJBA, TJMT, TJAP, TJES, TJRS, TJRN, TJPA, TJRO, TJSC, TJPI, TJGO, TJPB, TJTO, TJPR, TJRR e TJMG, alem de TJSP `cpopg`/`cposg` (variantes `method='html'` e `'api'`) e DataJud `listar_processos`. Contratos via `responses` + samples reais versionados em `tests/<sigla>/samples/<endpoint>/`, validam schema minimo do DataFrame e payload enviado ao backend (`json_params_matcher`/`urlencoded_params_matcher`/`query_param_matcher`/`header_matcher`). Inclui regressoes para guard `QueryTooLongError` (TJSP), TLS adapter `SECLEVEL=1` (TJCE), aliases deprecados (`query`/`termo`/`data_inicio`/`data_fim`/`nr_processo`), fluxos com pre-request/CSRF/AJAX (TJPB, TJSC, TJPR, TJRR, TJMG — TJMG inclui mock do captcha numerico via `txtcaptcha`), `test_cjsg_unknown_kwarg_raises` em todos os tribunais 1C-a wired (mais TJDFT e TJES via #165), e cobertura release-tier (`tests/test_release_date_filter.py`, marker `release`) que exercita o filtro de janela de datas em todos os 25 tribunais. Helpers compartilhados em `tests._helpers` e fixtures em `tests/helpers.py` ficam disponiveis para futuros raspadores. Scripts de captura em `tests/fixtures/capture/<sigla>.py` importam helpers publicos de `download.py` evitando drift silencioso. Refs #19, #84, #93, #94, #104, #113, #116, #119, #120, #121, #122, #140, #144, #146, #147, #165.
- Datas em endpoints com schema pydantic wired (familia eSAJ, 1C-a, TJDFT, TJES, etc.) passam a aceitar **quatro variacoes de string** (`DD/MM/AAAA`, `DD-MM-AAAA`, `AAAA-MM-DD`, `AAAA/MM/DD`) e tambem `datetime.date` / `datetime.datetime`. O `apply_input_pipeline_search` coage a entrada para o `BACKEND_DATE_FORMAT` declarado no schema antes da validacao pydantic, via novo helper `juscraper.utils.params.coerce_brazilian_date(value, backend_format)`. Resolve a parte comportamental de #26 e fecha #173.
- `apply_input_pipeline_search` ganhou parametros nominais para datas (`data_julgamento_inicio`, `data_julgamento_fim`, `data_publicacao_inicio`, `data_publicacao_fim`) e flags `consume_pesquisa_aliases` / `nullable_pesquisa`. Clients que mantem datas como argumentos nominais passam direto pelo helper (em vez de re-injetar manualmente em `kwargs`); clients que quiserem delegar `normalize_pesquisa` ao pipeline opt-in via `consume_pesquisa_aliases=True`. Migracao aplicada a TJDFT/TJES neste mesmo PR. Refs #174.
- Helpers publicos de construcao de payload em `juscraper.courts.<sigla>.download`: `build_cjsg_payload` (TJDFT, TJRS, TJRN, TJPA, TJRO, TJGO, TJPB, TJTO), `build_cjsg_form_body`/`cjsg_url_for_page` (TJSC), `build_cjsg_params` (TJPI), `build_cjsg_inner_payload` (TJRS), `fetch_csrf_token` (TJPB), `post_cjsg` + `CJSG_HEADERS` (TJPA). Em DataJud, `juscraper.aggregators.datajud.download.build_listar_processos_payload`. Compartilhados com os scripts de captura, atendem a regra "single source of truth do body" — capture e producao falham juntos quando o body real do scraper muda.
=======
- Novo agregador `comunica_cnj` (`ComunicaCNJScraper`) para a API publica de Comunicacoes Processuais do CNJ. Metodo publico `listar_comunicacoes(pesquisa, paginas=None, data_disponibilizacao_inicio=None, data_disponibilizacao_fim=None, itens_por_pagina=100)`. Datas aceitam ISO `YYYY-MM-DD` e `DD/MM/YYYY`. Validacao via pydantic com `extra="forbid"`.
- `DatajudScraper.listar_processos` e `contar_processos` ganham filtros novos da API Elasticsearch que nao eram acessiveis antes: `data_ajuizamento_inicio`/`data_ajuizamento_fim`, `tipos_movimentacao` (nomes amigaveis: `decisao`/`sentenca`/`julgamento`/`tutela`/`transito_julgado`), `movimentos_codigo` (codigos TPU), `orgao_julgador` e `query` (override total da query Elasticsearch para `must_not`/`should`/`range`/`wildcard`/`nested`/etc.). O alias generico `data_inicio`/`data_fim` **nao** e aceito — DataJud filtra por ajuizamento, nao julgamento. Refs #49, #176.
- Extra opcional `[tjmg]` em `pyproject.toml` declarando `txtcaptcha>=0.1.0`. Para raspar TJMG ao vivo: `pip install juscraper[tjmg]` (ou `uv pip install -e ".[tjmg]"`). Antes a dep era exigida em runtime mas nao formalizada nos metadados.
- TJSP `cjpg_download` e `cjsg_download` validam tamanho do campo `pesquisa` antes da requisicao: strings com mais de 120 caracteres levantam `QueryTooLongError` (subclasse de `ValueError`, em `juscraper.courts.tjsp.exceptions`) em vez de serem silenciosamente truncadas pelo backend. Refs #35.
- Validacao de input via schemas pydantic com `extra="forbid"` em todos os tribunais com refactor concluido (familia eSAJ TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`/`cjpg`; familia 1C-a TJRN/TJPA/TJRO/TJSC/TJPI `cjsg`; TJDFT/TJES/TJBA/TJMT/TJAP/TJRS/TJPB/TJTO `cjsg`; TJTO `cjpg`; TJPR/TJGO/TJRR/TJMG `cjsg`; e DataJud `listar_processos`). Kwargs desconhecidos passam a levantar `TypeError` com sugestao de typo (`(você quis dizer 'data_julgamento_inicio'?)`); filtros com formato invalido viram `ValidationError`. Antes eram silenciosamente ignorados. Refs #93, #117, #120, #125, #152, #165, #183.
- Filtros de data nos endpoints com pydantic wired (mesma lista acima) passam a aceitar **quatro variacoes de string** (`DD/MM/AAAA`, `DD-MM-AAAA`, `AAAA-MM-DD`, `AAAA/MM/DD`) e tambem `datetime.date` / `datetime.datetime`. Antes so `DD/MM/AAAA`. Refs #26, #173.
>>>>>>> main

### Fixed

- Raspadores TRF1/TRF3/TRF5 `cpopg` agora retornam **todas** as movimentações do processo, não apenas as 15 primeiras. O PJe pagina a tabela de movimentações com um Richfaces inslider (15 linhas por página); até a versão anterior só a página 1 (carregada inline no detalhe) era raspada, então processos com mais de 15 movimentações apareciam truncados sem aviso. O fix detecta o slider via regex no script `onchange` (extraindo `containerId`/`maxValue`/`ViewState`/IDs auto-gerados em runtime) e itera as páginas restantes via POST com `AJAXREQUEST=<containerId>` (não `_viewRoot`, que era o erro silencioso ao reproduzir o request fora do navegador). Os fragmentos AJAX retornados são spliceados na tbody da página 1, mantendo o parser downstream inalterado. Validação live: `1003063-27.2023.4.01.3304` (TRF1) sobe de 15 para 55 movs; `0814776-71.2022.4.05.8100` (TRF5) de 15 para 499 movs. Refs PR #126.

### Changed

- **BREAKING (colunas de saida padronizadas):** DataFrames de `cjsg` em TJES, TJMT, TJRS, TJRN, TJPE e TJRO passam a usar nomes canonicos uniformes. Renomeacoes: `nr_processo`/`numero_unico` -> `processo` (TJES, TJMT); `classe_cnj`/`classe_judicial` -> `classe` (TJRS, TJRN, TJES, TJPE, TJRO); `assunto_cnj`/`assunto_principal` -> `assunto` (TJRS, TJPE, TJES); `magistrado` -> `relator` (TJES). Codigo que acessa colunas pelo nome antigo precisa ser atualizado. Refs #93, #117.
- **BREAKING:** `DatajudScraper.listar_processos` levanta `ValueError` em vez de retornar DataFrame vazio quando a sigla do tribunal nao existe nos mappings ou quando nem `tribunal` nem `numero_processo` sao fornecidos. Erros de input do chamador deixam de falhar silenciosamente. Refs #57.
- **BREAKING:** `TJGOScraper.cjsg`/`cjsg_download` rejeitam `data_julgamento_inicio`/`fim` com `TypeError` em vez de emitir `UserWarning` e seguir a busca sem o filtro. O backend Projudi do TJGO so expoe filtro de data de publicacao; codigo que passava `data_julgamento_*` recebia resultado nao-filtrado silenciosamente. Migracao: usar `data_publicacao_inicio`/`fim` ou remover o argumento. Refs #93, #165, #183.
- **BREAKING:** `TJESScraper.cjsg`/`cjpg` e `TJMTScraper.cjsg` rejeitam `data_publicacao_inicio`/`fim` com `TypeError` em vez de descartar silenciosamente. Os backends expoem um unico intervalo de datas, exposto canonicamente via `data_julgamento_*`. Refs #165, #173.
- Schemas pydantic de `cjsg`/`cjpg` ganham aperto de tipos: `Literal[...]` para campos com dominio enumerado (TJMG, TJGO, TJPA, TJTO), `Field(ge=1)` para tamanhos de pagina (TJBA, TJDFT, TJES, TJGO, TJMT) e `str = ""` -> `str | None = None` em ~25 campos opcionais (TJGO, TJPB, TJRN, TJPI, TJRO, TJSC, TJRR, TJTO). Valor invalido vira `ValidationError` em vez de ser silenciosamente dropado pelo backend. Nao breaking — valores antes validos continuam validos. Refs #184.
- Familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`) consolidada na classe compartilhada `juscraper.courts._esaj.EsajSearchScraper`. **Dependencia nova: `pydantic>=2.0.0`.** API publica preservada byte-a-byte. Saldo: ~2500 linhas removidas em `src/juscraper/courts/`. Refs #84, #93, #104.
- `cjpg`/`cjsg` da familia eSAJ (cjsg em TJSP/TJAC/TJAL/TJAM/TJCE/TJMS, cjpg em TJSP) dividem internamente intervalos `data_julgamento_*` que excedem 366 dias, baixam cada janela e concatenam o resultado deduplicando. Falhas em janelas individuais viram `UserWarning` e o DataFrame retorna parcial. Controlado pelo flag `auto_chunk: bool = True`; comportamento antigo (`ValueError` em janelas longas) via `auto_chunk=False`. Refs #130.
- `DatajudScraper.listar_processos`: `paginas` aceita as 4 formas (`int | list[int] | range | None`); lista esparsa (`paginas=[3, 5]`) vira `range(min, max+1)` antes da iteracao porque o cursor `search_after` da API e forwards-only. `tamanho_pagina` sobe de `1000` para `5000` por default; em caso de `HTTP 504` ou `requests.Timeout`, a chamada refaz uma unica vez com `size // 4` (sticky para paginas subsequentes do mesmo alias) e emite `UserWarning`. Refs #93, #118, #140, #152, #153.
- Sdist (`juscraper-X.Y.Z.tar.gz` no PyPI) inclui somente `src/juscraper/`, README, LICENSE, CHANGELOG, CONTRIBUTING, CONDUCT e `pyproject.toml`. Sem essa configuracao, o tarball cresceria com `tests/<tribunal>/samples/` (~25 MB). Refs #139.

### Deprecated

- Parametros de Input renomeados para canonicos; os nomes antigos continuam aceitos com `DeprecationWarning` por um ciclo:
  - `nr_processo` -> `numero_processo` em TJPB, TJRN, TJRO.
  - `numero_cnj` -> `numero_processo` em TJAP.
  - `magistrado` -> `relator`, `classe_judicial` -> `classe` em TJES (`cjsg` e `cjpg`) e TJRO (`cjsg`). Refs #129.
  - `classe_cnj` -> `classe`, `assunto_cnj` -> `assunto` em TJPE.
  - `id_classe_judicial` -> `id_classe` em TJRN e TJPB (`cjsg`), por simetria com `id_relator`/`id_orgao_julgador`/`id_colegiado`. Refs #129.

### Removed

- Shim `src/juscraper/courts/tjsp/cjsg_download.py` (compatibility bridge para testes legados que importavam `cjsg_download`/`QueryTooLongError`). Imports devem passar a usar `juscraper.courts.tjsp.exceptions`.

### Fixed

- **DataJud** `listar_processos` e `contar_processos`: o filtro `assuntos` voltou a aceitar `int` (ex.: `assuntos=[12503]`) e o filtro `movimentos_codigo` passou a aceitar `str` (ex.: `movimentos_codigo=["246"]`) — ambos sao normalizados pelo schema antes do payload Elasticsearch. Antes do fix, o wiring pydantic rejeitava com `ValidationError` o caso natural de cada campo (codigos TPU sao inteiros por natureza; strings sao comuns vindo de planilha/CSV), embora o backend Elasticsearch coage os dois transparentemente. Refs #217.
- TJRJ `cjsg`: o POST inicial agora envia o hidden `ctl00$ContentPlaceHolder1$hfListaPalavrasBloqueadas`, mimetizando o form ASPX real. O backend ASPX comecou a 500 transientemente em 2026-04-30 quando esse campo era omitido. Junto com isso, `InputCJSGTJRJ` foi wired no metodo publico via `apply_input_pipeline_search` — kwargs desconhecidos (incluindo `data_julgamento_*` e `data_publicacao_*`, que o backend nao expoe — granularidade so anual via `ano_inicio`/`ano_fim`) passam a levantar `TypeError` em vez de serem silenciosamente dropados pelo antigo `warn_unsupported`. `competencia` e `origem` agora aceitam tanto `str` quanto `int` (`competencia=2` deixa de virar `ValidationError`). Refs #93, #143.
- Filtros de data passam a ser efetivamente enviados ao backend (e respeitados) em varios tribunais que silenciosamente devolviam resultados nao-filtrados ou em formato invalido:
  - **TJDFT** envia `termosAcessorios="entre YYYY-MM-DD e YYYY-MM-DD"`. Antes emitia `UserWarning` dizendo que o filtro nao era suportado e devolvia resultados sem filtro.
  - **TJTO** envia `tempo_julgados=pers` quando `data_julgamento_*` e fornecido. Sem isso, o backend ignorava `dat_jul_ini`/`dat_jul_fim`.
  - **TJRN** envia `dt_inicio`/`dt_fim` em `DD-MM-YYYY` (tracos, nao barras). Coluna `data_julgamento` agora vem de `dt_assinatura_teor` (`dt_julgamento` nao existe no indice Elasticsearch).
  - **TJPI** envia `data_min`/`data_max` na query string. Antes ignorava o filtro completamente.
  - **TJMT, TJPA, TJRO** serializam datas em ISO-8601 (`YYYY-MM-DD`); backend retornava HTTP 400/500 com `DD/MM/YYYY`.
  - **TJBA** aceita formato brasileiro alem de ISO. Antes produzia strings invalidas como `"12/03/2025T03:00:00.000Z"`.
  - **TJPB** pos-filtra o DataFrame retornado em `dt_ementa` (exposto como `data_julgamento`) — o backend nao filtra por data de julgamento. Funciona mesmo com so uma das datas informada (`date.min`/`date.max` no lado ausente). Refs #195.
- **TJRR** `cjsg`: backend voltou a retornar resultados — descoberta dinamica dos nomes auto-gerados dos campos JSF (que mudam quando o tribunal reordena componentes). O scraper estava silenciosamente retornando zero resultados depois da ultima renumeracao.
- **TJRS** `cjsg`: corrigida a primeira pagina da busca. O scraper enviava `pagina_atual=0`; o backend interpretava como `start=-10` e retornava erro Solr.
- **DataJud**: completados os mapeamentos de TRTs (24) e TREs (27), incluindo TST e TSE. Antes, processos das Justicas do Trabalho e Eleitoral consultados via `numero_processo` eram descartados silenciosamente. Refs #56.
- **DataJud**: numeros CNJ com whitespace (vindos de CSV/Excel) deixam de ser silenciosamente descartados; a query Elasticsearch envia o CNJ ja limpo (apenas digitos) em vez do original com pontos e tracos — antes, numeros formatados retornavam zero hits silenciosamente. Refs #59, #60.
- **DataJud**: problemas de runtime (CNJ invalido, tribunal nao mapeado, falha de API, timeout, JSON corrompido) emitem `warnings.warn(UserWarning)` alem do log. Em uso tipico via Jupyter Notebook, sem handler de logging configurado, esses problemas eram completamente invisiveis. Refs #57.
- eSAJ (TJSP `cjpg`/`cjsg`, TJAC/TJCE/TJMS/TJAM `cjsg`): scrapers passam a validar o certificado SSL (`session.verify = True`, default do `requests`). O `verify=False` era heranca do port do script R sem justificativa tecnica.
- eSAJ `cjsg_n_pags`: paginas com captcha nao resolvido / erro do site agora levantam `ValueError("Captcha nao foi resolvido...")` ou `ValueError("Erro detectado na pagina: ...")` em vez do confuso `"Nao foi possivel encontrar o seletor de numero de paginas"`. Vale para os 6 tribunais eSAJ.
- eSAJ (TJSP, TJAC, TJAL, TJAM, TJCE, TJMS): janelas `data_*` maiores que 1 ano levantam `ValueError` acionavel **antes** do HTTP, em vez de virarem erro confuso de "selector nao encontrado" depois da requisicao. Refs #91.
- eSAJ `cjsg_download` e TJSP `cjpg_download`/`cjsg_download`: aliases deprecados `query`/`termo` agora sao popados de `kwargs` com `DeprecationWarning` antes da validacao pydantic — a docstring ja prometia isso, mas o caminho estava quebrado e o usuario recebia `TypeError` em vez do warning. Refs #68, #93.
- Familia eSAJ — docstrings de `cjsg`/`cjpg` listam todos os filtros aceitos via `**kwargs` (com tipo, default, hint do backend e referencia ao schema pydantic). `help(tjsp.cjpg)` agora revela `varas`/`classes`/`assuntos`/`id_processo`/`data_julgamento_*`. Sem mudanca de runtime. Notebook `docs/notebooks/tjsp.ipynb` atualizado. Fecha #66.
- TJSP `cjpg`: `cjpg_n_pags` retorna `0` quando a busca nao tem resultados, em vez de levantar `ValueError`. `cjpg_download` faz early-return e `.cjpg(...)` devolve DataFrame vazio. Mesmo padrao ja usado em `cjsg`. Refs #109.
- TJSP `get_cpopg_download_links`: ramo `else` nunca populava a lista de links (atribuia `processos = lista.find_all('a')` e descartava o resultado). Agora itera sobre os `<a href>` e devolve a lista corretamente.
- TJSP `cpopg_download`/`cposg_download`: `RuntimeError` introduzido ao trocar `dict.get(k, [None])[0]` por early-raise (PR #105) escapava dos `except` de batch e abortava o download de todos os CNJs seguintes quando um link de listagem vinha sem `processo.codigo`. Agora o `RuntimeError` e capturado no loop externo e o batch segue.
- TJMT/TJBA `cjsg_parse`: respostas sem resultados podem vir do backend real com `null` em qualquer nivel intermediario; os parsers tratam `null` como lista vazia / dict ausente e retornam DataFrame vazio em vez de quebrar.
- `normalize_datas`: quando o usuario passa dois aliases distintos para o mesmo campo canonico (ex.: `data_inicio` + `data_julgamento_de`), a mensagem de `ValueError` agora cita os nomes que ele realmente escreveu, em vez do canonico que ele nunca digitou. O canonico aparece apenas como sugestao no trecho "Use apenas 'X'". Vale para todos os tribunais (a normalizacao e centralizada). Refs #193.

### Known Issues

- Dois tribunais tem o teste de filtro de datas marcado como `xfail` estrito em `test_release_date_filter.py`: **TJAP** (Tucujuris genuinamente nao expoe filtro por data — confirmado na engenharia reversa do site) e **TJRJ** (backend ASPX expoe apenas granularidade anual via `ano_inicio`/`ano_fim`; `InputCJSGTJRJ` rejeita `data_julgamento_*`/`data_publicacao_*` com `TypeError` por design — refs #143, #220). Ambas sao limitacoes server-side — nao dependem do cliente.

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
