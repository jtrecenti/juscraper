# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- `cjpg`/`cjsg` da familia eSAJ (cjsg em TJSP/TJAC/TJAL/TJAM/TJCE/TJMS, cjpg em TJSP) agora dividem internamente intervalos `data_julgamento_*` que excedem 366 dias, baixam cada janela e concatenam o resultado deduplicando por `cd_acordao` (cjsg) ou `id_processo` (cjpg). Refs #130.
  - Falhas em janelas individuais viram `UserWarning` e o DataFrame retorna parcial (com a coluna de dedup preservada mesmo quando todas falham).
  - Controlado pelo novo flag `auto_chunk: bool = True` (mixin `juscraper.schemas.AutoChunkMixin`).
  - Para o comportamento antigo (`ValueError` em janelas longas), passe `auto_chunk=False`.
  - `auto_chunk=True` combinado com `paginas` quando o intervalo excede 366 dias e `ValueError` por ambiguidade.
  - Conflito `pesquisa` + alias deprecado (`query`/`termo`) tambem levanta `ValueError` no caminho chunked (paridade com o caminho noop).
- Orquestracao do auto-chunking consolidada em `juscraper.courts._esaj.base.run_auto_chunk`. Antes, a logica vivia duplicada (~50 linhas) em `EsajSearchScraper.cjsg` e `TJSPScraper.cjpg`, com diferenca sutil no re-injetar de `**extras` (ponto de drift apontado em revisao de PR #155). O helper centraliza o sniff + windows + pop + validacao upfront + `_fetch` + `run_chunked_search`.

### Added

- Contratos de teste offline para a familia 1C-b (HTML/Session com pre-request ou endpoint extra): TJGO e TJPB (`cjsg`), TJTO (`cjsg` + `cjpg` + `cjsg_ementa`). Contratos via `responses` + samples reais versionados em `tests/<sigla>/samples/`, validam schema minimo do DataFrame e payload enviado (`urlencoded_params_matcher` para TJGO/TJTO, `json_params_matcher` para TJPB, `query_param_matcher` para `cjsg_ementa`). Scripts de captura em `tests/fixtures/capture/<sigla>.py` importam os novos helpers publicos de `download.py` (regra 12), evitando drift silencioso. TJPB grava `home.html` capturado para reusar a meta `_token` CSRF nos testes; TJTO sanitiza pos-captura mantendo so o `#result` (reduz 1 MB → 137 KB por sample, preserva o `_get_total_results` regex e o panel-document do parser). Testes de `DeprecationWarning` para aliases `query`/`termo` nos 3 tribunais, `nr_processo` em TJPB, `data_inicio`/`data_fim` em TJPB/TJTO; TJGO ganha cobertura adicional do par `DeprecationWarning` + `UserWarning` (regra 6a) — `data_julgamento_*` emite `warn_unsupported` porque o backend filtra so por publicacao, e `data_publicacao_*` e o canonico. TJRJ ficou fora do escopo: o POST inicial em `ConsultarJurisprudencia.aspx` retorna `500 Runtime Error` consistentemente desde 2026-04-30 (testado com diferentes UAs/headers); issue separada vai cobrir o scraper TJRJ junto com a captura. Wiring de schema pydantic deliberadamente fora do escopo — seguira junto com o refactor #84 da familia. Refs #94, #104, #113, #116, #121.
- Helpers publicos `build_cjsg_payload` (TJGO, TJPB, TJTO), `fetch_csrf_token` (TJPB) extraidos de `courts/<sigla>/download.py` e reusados pelos scripts em `tests/fixtures/capture/`. Antes, os scripts redefiniam inline o dicionario enviado ao backend e a regex de extracao do `_token` da meta tag — qualquer mudanca dessincronizaria os samples silenciosamente. TJTO promove `build_cjsg_payload` aceitando `start` (offset Solr) em kwargs; TJPB aceita `token` como primeiro argumento posicional para refletir a fronteira CSRF.
- Contratos de teste offline para a familia 1C-a (HTML/Session e JSON simples): TJRN, TJPA, TJRO, TJSC e TJPI (`cjsg`). Contratos via `responses` + samples reais versionados em `tests/<sigla>/samples/cjsg/`, validam schema minimo do DataFrame e payload enviado (`json_params_matcher` para TJRN/TJPA/TJRO, `urlencoded_params_matcher` para TJSC, `query_param_matcher` para TJPI). Scripts de captura em `tests/fixtures/capture/<sigla>.py` importam os novos helpers publicos de `download.py` (regra 12), evitando drift silencioso. TJPA e TJRO aplicam saneamento pos-captura para remover highlights de Elasticsearch e truncar blobs de texto; TJSC cobre a dual-URL (`listar_resultados` em `page=1`, `ajax_paginar_resultado` em `page>1`). Testes de `DeprecationWarning` para aliases `query`/`termo` nos 5 tribunais, `nr_processo` em TJRN/TJRO, e `data_inicio`/`data_fim` em TJPA/TJSC/TJRN/TJRO/TJPI (os cinco tribunais que chamam `normalize_datas` apos o PR #94). Wiring de schema pydantic deliberadamente fora do escopo — seguira junto com o refactor #84 da familia. Refs #94, #104, #113, #116, #120.
- Helpers publicos `build_cjsg_payload` (TJRN, TJPA, TJRO), `build_cjsg_form_body` + `cjsg_url_for_page` (TJSC) e `build_cjsg_params` (TJPI, agora estendido com `data_min`/`data_max` apos o wiring do PR #94) extraidos de `courts/<sigla>/download.py` e reusados pelos scripts em `tests/fixtures/capture/`. TJPA ganha tambem a constante `CJSG_HEADERS` (antes inline em `_fetch_page`) e o helper publico `post_cjsg(session, payload)` que centraliza URL + serializacao com `ensure_ascii=False` + headers — `_fetch_page` e o capture script chamam o mesmo helper, eliminando o ultimo ponto de drift entre scraper e captura na familia 1C-a.
- Cobertura de auto-descoberta de paginacao em TJSC e TJPI: novo `test_cjsg_paginas_none_descobre_via_html` exercita `_get_total_pages` (regex `(\d+)\s*documentos?\s*encontrados?` em TJSC; `[?&]page=(\d+)` em TJPI) sobre o sample `single_page`, fechando o gap em que `paginas=1` bypassava o ramo `paginas is None` do `cjsg_download_manager`. TJSC tambem passa a assertir `orgao_julgador` no schema minimo das paginas 1 (a pagina AJAX nao emite o campo, mas a uniao via concat preserva-o no DataFrame final).
- Suite de testes release-tier (`tests/test_release_date_filter.py`) que exercita o filtro de janela de datas (10/03/2025 – 14/03/2025) em todos os 25 tribunais registrados. Marker `release` registrado no `pyproject.toml` para separar CI rapido (`-m "integration and not release"`) de regressao completa antes de releases maiores (`-m "integration and release"`).
- `tests/helpers.py` com fixtures (`data_alvo_br`, `data_alvo_fim_br`, etc.) e helpers compartilhados (`run_filtro_data_unica`, `run_paginacao_data_unica`, `assert_date_matches`) que usam busca vazia e fallback automatico para `"direito"` quando o tribunal rejeita `pesquisa=""`.
- `juscraper.utils.params.to_iso_date`: contraparte de `to_br_date` para scrapers cujo backend espera ISO-8601.
- `juscraper.utils.params.pop_normalize_aliases(kwargs, *, include_canonical=False)` + constantes `SEARCH_ALIASES`/`DATE_ALIASES`/`DATE_CANONICAL` centralizam a lista de aliases consumidos por `normalize_pesquisa`/`normalize_datas`. Substituem 3 listas hardcoded duplicadas em `courts/_esaj/base.py`, `courts/tjrs/client.py` e `courts/tjsp/client.py` (cjpg_download). Um unico ponto de drift quando um alias novo for adicionado. Refs #93 #119.
- TJDFT `test_cjsg_data_inicio_alias_emits_deprecation_warning`: agora asserta tanto o `DeprecationWarning` de `normalize_datas` quanto o `UserWarning` de `warn_unsupported` — se um dos dois parar de disparar, o teste pega.
- Regras 6a ("cobertura minima de aliases deprecados") e 12 ("payload builders publicos") em `CLAUDE.md` > "Contrato ao adicionar um novo raspador". Formalizam a convencao de que helpers de download reusados pelos scripts de captura sao publicos (sem `_` inicial) e que todo alias aceito pelo scraper tem que ter teste de `DeprecationWarning` no `filters_contract`.
- Contratos de teste offline para a familia 1B (APIs JSON/GraphQL): TJDFT, TJBA, TJMT, TJAP, TJES e TJRS (`cjsg`), mais TJES `cjpg`. Os contratos usam `responses` + samples JSON reais recapturados em `tests/<tribunal>/samples/<endpoint>/`, validam schema minimo do DataFrame e payload enviado (`json_params_matcher`, `query_param_matcher`, `urlencoded_params_matcher`, `header_matcher`). Cada tribunal recebeu script de captura em `tests/fixtures/capture/<sigla>.py`; o README de captura documenta a convencao JSON da familia 1B. Refs #104, #113, #116.
- Testes de `DeprecationWarning` para aliases `query`/`termo`/`data_inicio`/`data_fim` em TJMT, TJRS e TJDFT, padronizando com o que TJAC ja cobria; novo `test_cjpg_typical_com_paginacao` em TJES completa a paridade com o `cjsg` do mesmo tribunal. Fecham os gaps de consistencia da Fase 1 da familia 1B.
- Helpers `build_cjsg_payload` (TJDFT) e `build_cjsg_inner_payload` (TJRS) extraidos de `courts/<xx>/download.py` e reusados pelos scripts em `tests/fixtures/capture/`. Antes, os scripts de captura redefiniam inline o dicionario enviado ao backend — qualquer mudanca no scraper dessincronizaria os samples silenciosamente.
- Samples TJRS (`tests/tjrs/samples/cjsg/*.json`) pos-processados para remover blocos de UI irrelevantes ao parser (`facet_counts`, `highlighting`, metadados de URL) e truncar o campo base64 `documento_text`. Reducao de ~9.5 MB para ~295 KB no agregado, mantendo o contrato intacto; o script `tests/fixtures/capture/tjrs.py` aplica o mesmo saneamento automaticamente em futuras capturas.
- Schemas pydantic de Input e Output para **todos** os endpoints publicos implementados (nao stubs) nos 25 tribunais e 2 agregadores do juscraper (refs #93, #117). Tribunais ainda nao refatorados recebem schema-arquivo sem wiring — servem como documentacao executavel da API publica e ponto de encaixe para a refatoracao futura (#84). Bases compartilhadas extraidas por evidencia concreta: `SearchBase` (25 ocorrencias de `pesquisa`/`paginas`), `DataJulgamentoMixin` (13 tribunais), `DataPublicacaoMixin` (11), `CnjInputBase`/`OutputCnjConsultaBase` para endpoints de consulta processual (`cpopg`/`cposg`/JusBR). Dois mixins de Output novos (`OutputRelatoriaMixin`, `OutputDataPublicacaoMixin`) promovidos por evidencia (>= 10 e >= 9 parsers concretos). Outputs declaram os campos observaveis diretamente do parser (lidos no codigo-fonte, sem depender de samples HTTP capturados); `extra="allow"` continua cobrindo campos auxiliares dinamicos (`cod_*`, `id_*`). Testes de cobertura (`tests/schemas/test_schema_coverage.py`) garantem que todo metodo publico nao-stub tem schema mapeado; paridade com a assinatura do metodo publico (`tests/schemas/test_signature_parity.py`); paridade com o parser (`tests/schemas/test_output_parity.py`); aceitacao unificada de `paginas` (`tests/schemas/test_paginas_acceptance.py`). Politica de manutencao documentada em `CLAUDE.md` ("Schemas pydantic (refs #93)").
- `tests/schemas/test_canonical_types.py` — rede de seguranca contra drift de nomes canonicos. Dois enforcamentos: (1) campos com nome canonico (palettes Input/Output derivadas automaticamente de `SearchBase`/bases/mixins) tem que usar o tipo declarado na base; (2) sinonimos deprecados (`magistrado`, `nr_processo`, `numero_unico`, `classe_cnj`, `classe_judicial`, `assunto_cnj`, `assunto_principal`, `numero_cnj`) nao podem aparecer em schemas concretos. Excecoes conhecidas ficam em `TYPE_GRACE_PERIOD` / `SYNONYM_GRACE_PERIOD` com razao + PR pendente; um teste meta valida que excecoes orfas sao removidas quando o PR de correcao entra. Previne o cenario "novo tribunal adicionado com `classes` em vez de `classe`" e "novo tribunal declarou `relator: int` quebrando o contrato canonico `str | None`". Refs #93, #117.
- Schemas pydantic `InputCJSGEsajPuro`/`OutputCJSGEsaj` (em `juscraper.courts._esaj.schemas`) e `InputCJSGTJSP`/`InputCJPGTJSP` (em `juscraper.courts.tjsp.schemas`), com `extra="forbid"`: agora kwargs desconhecidos nos metodos publicos `cjsg`/`cjpg` da familia eSAJ levantam `ValidationError` em vez de serem silenciosamente ignorados. Retrocompat com aliases deprecados (`query`/`termo`, `data_inicio`/`data_fim`, `data_julgamento_de`/`_ate`, `data_publicacao_de`/`_ate`) mantida via `normalize_pesquisa`/`normalize_datas`, que popam os aliases antes da validacao pydantic. Primeira fatia da #93 entregue junto com a POC do #84.
- Suite de testes ampliada para a familia eSAJ: `tests/test_cjsg_schemas.py` valida os schemas pydantic (14 testes); `tests/<sigla>/test_cjsg_filters_contract.py` em TJAC/TJAL/TJAM/TJCE/TJMS/TJSP + `tests/tjsp/test_cjpg_filters_contract.py` exercitam a propagacao de todos os filtros do metodo publico ate o body/query do request (16 testes), via `urlencoded_params_matcher`/`query_param_matcher`. Antes, contratos so cobriam o happy path sem filtros; agora a refatoracao fica protegida contra quebras silenciosas de qualquer filtro. `make_esaj_body` em `tests/fixtures/capture/_util.py` aceita todos os campos do form eSAJ. Refs #84 #93 #104 (gap reportado no comentario da POC).
- Cobertura adicional do caminho compartilhado `EsajSearchScraper.cjsg_download` para aliases deprecados: `tests/tjac/test_cjsg_filters_contract.py` ganha `test_cjsg_query_alias_emits_deprecation_warning` (exerce `normalize_pesquisa` no caminho do super, que os testes do TJSP nao cobrem porque o override popa os aliases antes de delegar) e `test_cjsg_data_inicio_alias_maps_to_data_julgamento` (confirma que `data_inicio`/`data_fim` sao mapeados para `data_julgamento_*` pelo `normalize_datas` antes do pydantic, com `DeprecationWarning` e body canonico no wire). Refs #115.
- Contratos de teste offline para TJSP nos 4 metodos publicos (`cjsg`, `cjpg`, `cpopg` e `cposg`), incluindo variantes `method='html'` e `method='api'` de `cpopg` e `cposg`. Samples capturados via `tests/fixtures/capture/tjsp.py`, cobrindo desde o POST `cjsg/resultadoCompleta.do` ate o fluxo API `search/numproc` → `dadosbasicos` → componentes. Contratos validam schema minimo do DataFrame + payload enviado (via `urlencoded_params_matcher`/`query_param_matcher`). Inclui regressao para o guard `QueryTooLongError` (pesquisa > 120 chars) no `cjsg` e `cjpg`. Segunda fatia da Fase 1 da politica de testes (refs #19, #104).
- Secao "Contrato ao adicionar um novo raspador" em `CLAUDE.md`: checklist obrigatoria de 8 itens (script de captura, samples commitados, matchers, schema via subset, etc.) para todo PR que introduz um raspador novo (refs #104).
- Helpers em `tests/fixtures/capture/_util.py`: `make_tjsp_cjsg_body`, `make_tjsp_cjpg_params`, `TJSP_CHROME_HEADERS`, mais parametros `body_builder`/`headers` em `fetch_cjsg_pages`/`capture_cjsg_samples`. `samples_dir_for` agora aceita `endpoint` alem de `cjsg`. Permite compartilhar logica de captura entre eSAJ-puros e TJSP sem duplicacao.
- Contratos de teste offline para TJAC, TJAL, TJAM, TJCE e TJMS (`cjsg`). Cada tribunal ganhou `tests/<sigla>/test_cjsg_contract.py` cobrindo 3 cenarios (typical com paginacao, pagina unica, sem resultados), alimentados por samples HTML versionados em `tests/<sigla>/samples/cjsg/` e capturados via scripts em `tests/fixtures/capture/<sigla>.py`. Inclui teste de regressao para o adapter TLS `SECLEVEL=1` do TJCE. Primeira fatia da Fase 1 da politica de testes (refs #19, #104).
- TJSP CJPG/CJSG: validacao de tamanho do campo `pesquisa` antes da requisicao. O backend do eSAJ trunca strings com mais de 120 caracteres silenciosamente; agora `cjpg_download` e `cjsg_download` levantam `QueryTooLongError` (subclasse de `ValueError`) quando o limite e excedido. Refs #35.

### Changed

- Sdist (`juscraper-X.Y.Z.tar.gz` no PyPI) passa a incluir somente `src/juscraper/`, README, LICENSE, CHANGELOG, CONTRIBUTING, CONDUCT e `pyproject.toml`. Diretorios `tests/`, `docs/`, `issues/`, `scripts/`, `.claude/`, `.github/` e caches deixam de ser empacotados — sem a configuracao explicita o tarball cresceria proporcionalmente a `tests/<tribunal>/samples/` (~25 MB hoje). Wheel ja excluia `tests/` por default do hatchling com layout `src/`; agora a configuracao esta explicita via `[tool.hatch.build.targets.wheel] packages = ["src/juscraper"]`. Adicionado guard no workflow `publish.yml` que falha o build se o wheel/sdist contiver `tests/` ou se o sdist exceder 1 MB. Refs #139.
- `pyproject.toml`: adicionado `pythonpath = ["tests"]` para permitir `from helpers import ...` sem hacks de `sys.path`.
- **BREAKING (colunas de saida padronizadas):** DataFrames de `cjsg` dos tribunais TJES, TJMT, TJRS, TJRN, TJPE e TJRO passam a usar nomes canonicos uniformes para colunas semanticamente equivalentes. Renomeacoes: `nr_processo`/`numero_unico` -> `processo` (TJES, TJMT); `classe_cnj`/`classe_judicial` -> `classe` (TJRS, TJRN, TJES, TJPE, TJRO); `assunto_cnj`/`assunto_principal` -> `assunto` (TJRS, TJPE, TJES); `magistrado` -> `relator` (TJES). Codigo que acessa colunas pelo nome antigo (ex.: `df["classe_cnj"]`) precisa ser atualizado. Refs #93, #117.
- `OutputCJSGBase.ementa` relaxado para `Optional[str]` (TJGO entrega o texto completo em `texto`, nao em `ementa`). `OutputCJSGBase.data_julgamento` aceita agora `date | str | None` para refletir os parsers que ja convertem para `datetime.date`. Redeclaracoes cosmeticas de `paginas` em schemas concretos (TJAP, TJES, TJMG, TJPE, TJPR, TJRO, TJRR, TJRS) removidas — `SearchBase` e a fonte unica. Refs #93, #117.
- Consolidada a checagem de alias deprecado em `juscraper.utils.params.resolve_deprecated_alias`. Clients que deprecaram parametros (TJAP, TJPB, TJRN, TJRO, TJES, TJPE) perdem blocos inline de 6 linhas + 2 helpers locais (`_resolve_aliases`/`_resolve_tjpe_aliases`); comportamento identico (emite `DeprecationWarning` quando so o alias e passado, `ValueError` quando canonico + alias colidem). Refs #93, #117.
- `OutputCJSGEsaj` (compartilhado por TJAC/TJAL/TJAM/TJCE/TJMS/TJSP) declara explicitamente `relatora: str | None = None` para refletir o que o parser eSAJ (`_normalize_key` sobre a label HTML "Relator(a):") hoje emite. TODO no docstring aponta o PR dedicado que deve normalizar `relatora -> relator` no parser — correcao estrutural e breaking (breaking change identica as renomeacoes canonicas ja feitas em outros tribunais) e merece PR proprio para manter o CHANGELOG claro. Refs #93, #117.
- Secao "Schemas pydantic (refs #93)" do `CLAUDE.md` enxugada de 118 para ~45 linhas de conteudo denso. Removido o snippet Python de 42 linhas do pipeline canonico (substituido por ponteiro para `src/juscraper/courts/_esaj/base.py` + contratos de teste); fundidas "Regras de desenho" + "Proibicoes explicitas" em uma unica lista; enxugado o checklist. Mantida toda a orientacao load-bearing (wiring em duas fases, diretorios, OOP dirigida por evidencia, regras byte-a-byte, pipeline canonico por referencia). Refs #93, #117.
- Familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`) consolidada numa classe compartilhada `juscraper.courts._esaj.EsajSearchScraper`. Os 5 eSAJ-puros viraram clients de ~15 linhas cada (definem so `BASE_URL` e `TRIBUNAL_NAME`); TJCE adicionalmente sobrescreve o hook `_configure_session` para montar o TLS adapter `SECLEVEL=1`; TJSP sobrescreve `_build_cjsg_body` (body diferente), liga o hook de `conversationId` + UA Chrome, e mantem cjpg/cpopg/cposg nos proprios modulos. `QueryTooLongError` do TJSP migrada para `juscraper.courts.tjsp.exceptions`. Saldo: ~2500 linhas removidas em `src/juscraper/courts/`. Dependencia nova: `pydantic>=2.0.0`. API publica preservada byte-a-byte; todos os contratos pre-existentes passam sem alteracao. POC do #84 aplicada a familia 1A (refs #84, #93, #104).
- Samples do TJSP migrados de `tests/tjsp/samples/*.html` (flat) para `tests/tjsp/samples/<endpoint>/*.html` (subdir), alinhando com a convencao introduzida em #102. Arquivos movidos via `git mv`: `cjsg_results.html` → `cjsg/results_normal.html`, `cjsg_single_result.html` → `cjsg/single_result.html`, `cjsg_no_results.html` → `cjsg/no_results.html`, `cjpg_results.html` → `cjpg/results_legacy.html`, `cjpg_results_novo_formato.html` → `cjpg/results_novo_formato.html`, `cpopg_standard.html` → `cpopg/show_standard.html`, `cpopg_alternative.html` → `cpopg/show_alternative.html`. Testes atualizados para consumir os novos caminhos via `tests._helpers.load_sample`; `tests/tjsp/test_utils.py::load_sample_html` e `get_test_samples_dir` removidos (substituidos pelo helper central). `create_mock_response`/`create_mock_session_with_responses` mantidos.
- eSAJ: `juscraper.utils.params.validate_intervalo_datas` aceita parametro `origem` (default `"O eSAJ"`) para reuso em tribunais nao-eSAJ com mensagem de erro correta. Janela maxima default aumentada de 365 para 366 dias para nao rejeitar cliente-side uma janela de 1 ano calendario que atravesse 29/02 (ex: `01/01/2024` -> `01/01/2025`).
- `tests/tjsp/`: removidos hacks de `sys.path.insert` e `from src.juscraper`. Os testes agora dependem do install editavel (`uv pip install -e ".[dev]"`), conforme o `CLAUDE.md` (refs #88).
- **BREAKING:** DataJud `listar_processos` agora levanta `ValueError` em vez de retornar DataFrame vazio quando a sigla do tribunal nao existe nos mappings ou quando nem `tribunal` nem `numero_processo` sao fornecidos. Erros de input do chamador deixam de falhar silenciosamente. Refs #57.
- Dev-tooling: `pyproject.toml` agora inclui `types-requests` e `pytest-mock` nas dev extras e `filterwarnings = ["error"]` na config do pytest. Contribuidores que rodem `pytest`/`mypy` localmente veem o mesmo resultado que o `pre-commit`, sem falsos positivos de stubs ausentes e sem warnings silenciosos.
- `BaseScraper.download_path` passou a ser anotado como `str` (inicializado com `""` e preenchido por `set_download_path` ou pela assinatura da subclasse). `set_download_path` aceita `Optional[str]` explicitamente. Zero impacto em runtime; remove ~15 erros `Optional` em cascata nos clients.
- Politica de testes (Fase 0): `pytest` por default executa apenas testes offline via `addopts = -m 'not integration'`. Para integracao usar `pytest -m integration`; para tudo, `pytest -m ""`. Adicionado `responses` em dev deps (o `pytest-mock` ja havia entrado pelo PR #103); novo marker `vcr` para `pytest-recording`. Criados `tests/conftest.py` (fixture `tests_dir`) e `tests/_helpers.py` (`load_sample`, `load_sample_bytes`). Nova secao "Testes" no `CLAUDE.md` documenta a piramide de testes (contrato/granular/cassete/integracao). Refs #19, #84, #101.

### Deprecated

- Parametros de Input renomeados para canonicos; os nomes antigos continuam aceitos com `DeprecationWarning` por um ciclo:
  - `nr_processo` -> `numero_processo` em TJPB, TJRN, TJRO.
  - `numero_cnj` -> `numero_processo` em TJAP.
  - `magistrado` -> `relator`, `classe_judicial` -> `classe` em TJES (`cjsg` e `cjpg`).
  - `classe_cnj` -> `classe`, `assunto_cnj` -> `assunto` em TJPE.

  Novos helpers `juscraper.utils.params.pop_deprecated_alias` (pop + warning) e `juscraper.utils.params.resolve_deprecated_alias` (pop + checagem de colisao + reatribuicao) centralizam o padrao. Refs #93, #117.

### Removed

- `MANIFEST.in` na raiz. Era vestigio do tempo do setuptools; o backend de build atual (hatchling) ignora completamente. Politica de empacotamento agora vive em `[tool.hatch.build.targets.*]` no `pyproject.toml`. Refs #139.
- Shim `src/juscraper/courts/tjsp/cjsg_download.py` (apenas compatibility bridge para testes legados que importavam `cjsg_download`/`QueryTooLongError`). Testes em `tests/tjsp/test_query_validation.py` e `tests/tjsp/test_cjsg_contract.py` atualizados para importar direto de `juscraper.courts.tjsp.exceptions`. A docstring de `src/juscraper/courts/tjsp/forms.py::build_tjsp_cjsg_body` reescrita para documentar as diferencas funcionais reais do body do TJSP vs. eSAJ-puros (sem `conversationId`, sem `dtPublicacao*`, `baixar_sg` mapeia para `origem`).
- `tests/tjsp/test_search_limit.py`: redundante com `tests/tjsp/test_query_validation.py` depois da consolidacao do guard de 120 chars em `validate_pesquisa_length`. Cobertura integral preservada pelo `test_query_validation.py`.

### Fixed

- Documentacao da familia eSAJ — docstrings de `cjsg`/`cjpg` agora listam todos os filtros aceitos via `**kwargs` (com tipo, default, hint do backend e referencia ao schema pydantic). Antes a docstring tinha apenas uma linha e `help(tjsp.cjpg)` nao revelava `varas`/`classes`/`assuntos`/`id_processo`/`data_julgamento_*`, dando a impressao de que esses filtros nao existiam (motivacao da #66). Sem mudanca de runtime — os filtros ja eram aceitos via `**kwargs` e validados pelo pydantic. Fecha #66.
  - `EsajSearchScraper.cjsg`/`cjsg_download` em `_esaj/base.py` (afeta TJAC/TJAL/TJAM/TJCE/TJMS por heranca).
  - `TJSPScraper.cjsg`/`cjsg_download`/`cjpg`/`cjpg_download` em `tjsp/client.py`. TJSP ganha um `cjsg` proprio (override raso) so para ancorar a docstring TJSP-especifica, ja que `InputCJSGTJSP` difere do schema default da familia.
  - Notebook `docs/notebooks/tjsp.ipynb` atualizado: celula CJPG passa a listar `id_processo` e `data_julgamento_inicio`/`fim`; celula CJSG troca os aliases deprecados `data_inicio`/`data_fim` pelos canonicos `data_julgamento_inicio`/`fim`.
  - Padrao registrado em `CLAUDE.md > Docstrings de metodos publicos com **kwargs` para guiar futuros endpoints da familia. Regra 5 endurecida (referencia `:meth:` em `*_download` e parte do contrato, nao apenas estilo) e nova regra 7 (override de docstring com schema proprio precisa entrar em `CASES`).
  - Testes de paridade docstring↔schema (`tests/schemas/test_docstring_parity.py::test_docstring_lists_schema_fields`), referencia `:meth:` em `*_download` (`test_download_docstring_references_toplevel`) e override↔base (`tests/tjsp/test_cjsg_signature_parity.py`) protegem contra drift futuro.
- TJBA CJSG: `_to_iso` aceita datas em formato brasileiro (DD/MM/YYYY) alem de ISO, usando `to_iso_date`. Antes produzia strings invalidas como `"12/03/2025T03:00:00.000Z"` quando o usuario passava no formato canonico do projeto.
- Helper de teste `_call_cjsg_with_fallback`: fallback para `"direito"` agora dispara tambem quando `pesquisa=""` retorna DataFrame vazio (antes so pegava excecoes).
- TJDFT CJSG: filtro de datas de julgamento e publicacao agora e enviado ao backend via `termosAcessorios` (formato `"entre YYYY-MM-DD e YYYY-MM-DD"`, descoberto na reversao dos chunks Angular do frontend). Antes o scraper emitia um `UserWarning` dizendo que os parametros nao eram suportados e devolvia resultados sem filtro.
- TJTO CJSG: `tempo_julgados` passa a ser enviado como `"pers"` quando `data_julgamento_inicio`/`fim` sao fornecidos. Sem isso o backend ignorava silenciosamente `dat_jul_ini`/`dat_jul_fim` e devolvia os julgamentos mais recentes (a UI so ativa o intervalo customizado quando o radio "Intervalo personalizado" e selecionado, e o backend espelha essa logica).
- TJRN CJSG: filtro de datas e coluna `data_julgamento` consertados. O backend do TJRN espera `dt_inicio`/`dt_fim` no formato `DD-MM-YYYY` (tracos, nao barras — slashes sao silenciosamente ignoradas). O parser passa a ler `dt_assinatura_teor` como `data_julgamento` (o campo `dt_julgamento` que o codigo esperava nao existe no indice Elasticsearch) e expoe `data_publicacao` a partir de `dt_publicacao`.
- TJPI CJSG: filtro de datas (`data_min`/`data_max`) agora e enviado na query string da busca HTML. Antes o scraper ignorava `data_julgamento_inicio`/`fim` e devolvia resultados de qualquer data.
- TJMT CJSG: `filtro.periodoDataDe`/`filtro.periodoDataAte` agora sao enviados em ISO-8601 (`YYYY-MM-DD`). O frontend Angular faz o mesmo: parseia o input `DD/MM/YYYY` e formata como `YYYY-MM-DD` antes de POST. O backend Hellsgate ignora silenciosamente qualquer outro formato e devolve os julgamentos mais recentes.
- TJPA CJSG: `dataJulgamentoInicio`/`dataJulgamentoFim` e `dataPublicacaoInicio`/`dataPublicacaoFim` agora sao serializados em ISO (`YYYY-MM-DD`). O backend Elasticsearch retornava HTTP 400 (`search_phase_execution_exception`) com DD/MM/YYYY.
- TJRO CJSG: `dtjulgamento_inicio`/`dtjulgamento_fim` agora sao serializados em ISO. O backend retornava HTTP 500 com DD/MM/YYYY.
- TJPB CJSG: filtro de datas agora bate com o que o usuario pede. O backend `dt_inicio`/`dt_fim` filtra por uma data interna diferente (provavelmente `dt_disponibilizacao`), mas so devolve `dt_ementa`, e as duas nao estao alinhadas — rows podiam vir com `dt_ementa` completamente fora da janela solicitada. O client passa a pos-filtrar o DataFrame retornado para manter so as linhas cujo `dt_ementa` (exposto como `data_julgamento`) esta no intervalo `data_julgamento_inicio`/`fim`. Semantica final: o usuario pede `10/03–14/03` e recebe so decisoes com ementa nesse intervalo.
- TJRR CJSG: descoberta dinamica dos nomes dos campos JSF e snapshot completo dos defaults do formulario. Os IDs auto-gerados pelo JSF (`menuinicial:j_idt28` para pesquisa, `j_idt30` para submit etc.) mudam cada vez que o tribunal adiciona/reordena componentes no servidor; o scraper ficou silenciosamente retornando zero resultados depois da ultima renumeracao. `_get_form_fields` agora resolve o input de pesquisa via `id=consultaAtual` e o botao submit pelo primeiro `<button>` com `name` `menuinicial:j_idt…` que nao comeca com `menuinicial:btn_`. Alem disso, `_collect_form_defaults` copia todo input do form `menuinicial` (incluindo flags de paineis colapsados como `menuinicial:j_idt44_collapsed=true` e `menuinicial:tipoClasseList=0`), imitando o que um browser envia. Sem esses campos, buscas com `pesquisa=''` + filtro de data devolviam zero resultados mesmo quando o filtro estava correto. Envia tambem `Origin`/`Referer` para replicar o contexto da submissao.
- Helper de release `run_filtro_data_unica`/`run_paginacao_data_unica` passa a enviar a janela de julgamento tight (10/03–14/03) e a janela de publicacao widened (10/03–30/04), com fallback em cascata: (1) ambas as janelas, (2) so julgamento, (3) so publicacao. Isso acomoda scrapers que AND-fundem (eSAJ/TJAM), scrapers que so implementam publicacao (TJBA, TJGO), e scrapers em que o indice de publicacao esta vazio (TJPA). `assert_date_matches` valida rows contra a janela apropriada conforme a coluna exposta (julgamento vs publicacao).
- TJRS `cjsg`: corrigida a primeira pagina da busca. O scraper enviava `pagina_atual=0`; o backend real do TJRS interpreta isso como `start=-10` e retorna erro Solr em vez de documentos. Agora `paginas=1` envia `pagina_atual=1`, preservando o contrato 1-based da API publica. O bug foi exposto pelos contratos offline com samples reais da familia 1B.
- TJMT `cjsg_parse`: respostas sem resultados podem vir do backend real com `AcordaoCollection: null` / `DecisaoMonocraticaCollection: null`; o parser agora trata `null` como lista vazia e retorna DataFrame vazio em vez de quebrar ao iterar sobre `None`.
- TJBA `cjsg_parse`: cadeia defensiva contra `null` em qualquer nivel intermediario da resposta GraphQL (`data`, `data.filter`, `data.filter.decisoes`). O padrao anterior `.get(key, {})` so cobria chave ausente, nao valor `null`; agora o parser retorna DataFrame vazio em vez de quebrar caso o backend devolva null (cenario analogo ao corrigido em TJMT). Inclui `tests/tjba/test_cjsg_parse_granular.py` exercitando os 3 niveis + dict vazio.
- TJRS `cjsg`: aliases deprecados (`query`/`termo`, `data_inicio`/`data_fim`, `data_*_de`/`_ate`) agora sao efetivamente descartados do `kwargs` apos `normalize_pesquisa`/`normalize_datas`. Antes, a dupla chamada de `normalize_*` no `cjsg` publico + `cjsg_download` fazia o alias sobreviver no dict local e colidir com o `termo=pesquisa` ja resolvido em `cjsg_download_manager(**kwargs)`, levantando `TypeError: got multiple values for keyword argument 'termo'`. O `DeprecationWarning` prometido nunca era emitido ao usuario — era sempre engolido pelo erro.
- eSAJ `cjsg_n_pags` (compartilhado em `juscraper.courts._esaj.parse`): restaurada a deteccao de captcha/erro que existia no parser TJSP antes da consolidacao do PR #115. Paginas que retornam divs com `class` contendo `error`/`erro`/`mensagem erro` agora levantam `ValueError("Captcha nao foi resolvido...")` ou `ValueError("Erro detectado na pagina: ...")` em vez do confuso `"Nao foi possivel encontrar o seletor de numero de paginas"`. Vale para todos os 6 tribunais eSAJ (antes so TJSP tinha esse caminho).
- eSAJ `cjsg_download` (base `EsajSearchScraper`) e TJSP `cjpg_download`/`cjsg_download`: aliases deprecados `query`/`termo` agora sao de fato popados de `kwargs` com `DeprecationWarning` antes da validacao pydantic — a docstring prometia isso mas `normalize_pesquisa` nunca era chamado, entao o usuario recebia `TypeError` em vez do warning documentado. Refs #68 #93.
- TJSP `cjpg_download` (modulo interno): removida chamada duplicada de `validate_pesquisa_length` que rodava tanto em `client.py` quanto no helper interno. A validacao agora acontece exclusivamente no ponto de entrada publico (`TJSPScraper.cjpg_download`), conforme documentado em `tjsp/schemas.py`. `TestCJPGQueryValidation` em `tests/tjsp/test_query_validation.py` passou a exercer a API publica em vez do helper interno.
- TJSP CJPG/CJSG: anotacoes de tipo dos parametros opcionais agora explicitam `| None` (antes eram `T = None` e disparavam erros do mypy `no_implicit_optional`). Refs #30.
- eSAJ (TJSP cjpg/cjsg, TJAC/TJCE/TJMS/TJAM cjsg): validacao antecipada do intervalo entre `data_*_inicio` e `data_*_fim`. O eSAJ rejeita janelas maiores que 1 ano, mas antes o erro aparecia como "Nao foi possivel encontrar o seletor de numero de paginas" apos a requisicao ser feita. Agora um `ValueError` acionavel e lancado antes de qualquer HTTP, explicando o limite e orientando dividir a consulta em janelas menores (novo helper `juscraper.utils.params.validate_intervalo_datas`). Refs #91.
- `juscraper.utils.cnj.clean_cnj`: agora remove qualquer caractere nao-digito (espacos, tabs, quebras de linha), nao apenas `.` e `-`. Numeros CNJ vindos de CSV/Excel com whitespace deixam de ser silenciosamente descartados pelo DataJud (refs #59).
- `sanitize_filename`: removido `isinstance` redundante que conflitava com a anotacao de tipo e quebrava o pre-commit do mypy (refs #33).
- DataJud: ao buscar por `numero_processo`, a query Elasticsearch agora envia o CNJ ja limpo (apenas digitos) em vez do original com pontos e tracos, em todos os caminhos de entrada (com ou sem `tribunal=`, string ou lista). Antes, numeros formatados retornavam zero hits silenciosamente porque o campo `numeroProcesso` no indice e armazenado sem formatacao (refs #60).
- DataJud: completados os mapeamentos de TRTs (24) e TREs (27), incluindo TST e TSE, em `ID_JUSTICA_TRIBUNAL_TO_ALIAS` e `TRIBUNAL_TO_ALIAS`. Antes, processos das Justicas do Trabalho e Eleitoral consultados via `numero_processo` eram descartados silenciosamente porque o alias nao podia ser resolvido. Aliases conferidos com a wiki oficial em datajud-wiki.cnj.jus.br (refs #56).
- DataJud: problemas de runtime (CNJ invalido ou de tribunal nao mapeado, falha de API, timeout, JSON corrompido, erro de parse) agora emitem `warnings.warn(UserWarning)` alem do `logger.error/warning`. Em uso tipico via Jupyter Notebook, sem handler de logging configurado, esses problemas eram completamente invisiveis e processos sumiam do resultado sem aviso. `UserWarning` e visivel por padrao em notebooks. Refs #57.
- DataJud: removido warning redundante "Nenhum CNJ válido foi reconhecido" quando todos os CNJs informados ja emitiram warning individual ("CNJ invalido" ou "tribunal nao mapeado"). Antes, chamar `listar_processos(numero_processo="123")` emitia dois `UserWarning`s com a mesma informacao, sendo o segundo invisivel ao `pytest.warns` do primeiro. O `logger.error` de resumo foi mantido.
- TJSP `cposg_download`: condicao `elif self.method == 'json'` era dead code — `set_method` so aceita `'html'` ou `'api'`, entao o caminho da API nunca era executado. Agora compara contra `'api'` corretamente.
- Mypy: limpeza ampla dos erros em `src/`. Substituicao automatica de implicit `Optional[T]` via `no_implicit_optional` codemod; ajuste de reatribuicoes que mudavam tipo de variavel (TJSP `cjpg_download`, TJRR `_search`); narrowing de `paginas: int | list | range | None` para `list | range | None` nos downloads (int e convertido para range por `normalize_paginas` no client); cast em `response.json()`/`.decode()` para evitar `Returning Any` em funcoes tipadas; correcao de `fetch_document_binary` que declarava retorno `Optional[str]` mas retornava `bytes`.
- eSAJ (TJSP, TJAL, TJAM, TJAC, TJMS, TJCE): scrapers de CJSG agora validam o certificado SSL dos servidores (`session.verify = True`, default do `requests`). Os tribunais testados respondem corretamente com cadeia de certificados válida — o `verify=False` era heranca do port do script R (refs commit df552ca) e nao tinha justificativa técnica. Efeito colateral: removidos `urllib3.disable_warnings(InsecureRequestWarning)` em nivel de modulo e o `warnings.filterwarnings('ignore', ...)` global em `tjsp/client.py` que contornava silenciosamente o `filterwarnings = ["error"]` do pytest. No TJCE, o `_TJCETLSAdapter` foi reduzido a apenas `set_ciphers("DEFAULT:@SECLEVEL=1")` (necessario para aceitar o cipher legacy do servidor); `check_hostname = False` e `verify_mode = CERT_NONE` foram removidos porque o certificado é válido.
- `tests/tjes/`, `tests/tjpa/`: `test_filtro_data` agora usa `data_julgamento_inicio/fim` (convencao canonica) em vez dos aliases deprecados `data_inicio/fim`. Com `filterwarnings = ["error"]` ativo, os aliases disparavam `DeprecationWarning` que virava erro ao rodar `pytest` completo (sem `-m "not integration"`).
- TJSP `get_cpopg_download_links`: ramo `else` nunca populava a lista de links retornada (atribuia `processos = lista.find_all('a')` e descartava o resultado). Agora itera sobre os `<a href>` e acrescenta cada href em `links`, entregando o comportamento que a docstring ja descrevia. Bug pre-existente.
- TJSP `cpopg_download`/`cposg_download`: o `RuntimeError` introduzido ao trocar `dict.get(k, [None])[0]` por early-raise (PR #105) escapava dos `except` de batch e abortava o download de todos os CNJs seguintes quando um link de listagem vinha sem `processo.codigo`. Agora `RuntimeError` e capturado no loop externo, logado e o batch segue para o proximo CNJ. `cposg_download_html` tambem levanta `RuntimeError` explicito quando nenhum processo e baixado com sucesso, em vez de quebrar com `IndexError` em `paths[0]`.
- TJSP CJPG: `cjpg_n_pags` agora retorna `0` quando a busca nao gera resultados (HTML de formulario com "Nao foi encontrado nenhum resultado"), em vez de levantar `ValueError`. `cjpg_download` faz early-return salvando apenas a primeira pagina, e `.cjpg(...)` devolve DataFrame vazio. Mesmo padrao ja usado em `cjsg_n_pags`/`cjsg_download`. Contrato `test_cjpg_no_results` adicionado. Refs #109.

### Known Issues

- Dois tribunais tem o teste de filtro de datas marcado como `xfail` estrito (lista `KNOWN_FILTRO_FAILURES` em `test_release_date_filter.py`): tjap (Tucujuris genuinamente nao expoe filtro por data — confirmado na engenharia reversa do HTML, JS e API do site: sem inputs, sem campos hidden, backend ignora silenciosamente qualquer variante de `dataInicial`/`dataInicio`/`dataJulgamento…`/`periodoInicio`) e tjrj (endpoint legado ASP.NET devolve HTTP 500 ate sem filtros). Ambas sao server-side — nao dependem do cliente. Cada fix deve remover o tribunal da lista — `strict=True` sinaliza quando o bug se resolve sozinho.

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
