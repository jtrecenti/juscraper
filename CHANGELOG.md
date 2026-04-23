# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- `OutputCJSGTJGO` sobrescreve `ementa` como `Optional[str]` e adiciona `texto: Optional[str]`. O parser do TJGO (`src/juscraper/courts/tjgo/parse.py`) entrega o conteudo do documento em `texto`, nao em `ementa`; herdar `OutputCJSGBase` sem ajuste exigiria `ementa: str` e quebraria a validacao se o schema fosse wired para validar cada linha. Teste dedicado em `tests/schemas/test_schema_contract.py::test_tjgo_output_accepts_parser_shape`. Documentada em `CLAUDE.md` a regra: quando o parser nao produz um campo herdado da base, sobrescrever como Optional em vez de deixar required. Refs #93, #117.

### Changed

- Secao "Schemas pydantic (refs #93)" do `CLAUDE.md` enxugada de 118 para ~45 linhas de conteudo denso. Removido o snippet Python de 42 linhas do pipeline canonico (substituido por ponteiro para `src/juscraper/courts/_esaj/base.py` + contratos de teste); fundidas "Regras de desenho" + "Proibicoes explicitas" em uma unica lista; enxugado o checklist. Mantida toda a orientacao load-bearing (wiring em duas fases, diretorios, OOP dirigida por evidencia, regras byte-a-byte, pipeline canonico por referencia). Refs #93, #117.

### Added

- Schemas pydantic de Input e Output para **todos** os endpoints publicos implementados (nao stubs) nos 25 tribunais e 2 agregadores do juscraper (refs #93). Tribunais ainda nao refatorados recebem schema-arquivo sem wiring — servem como documentacao executavel da API publica e ponto de encaixe para a refatoracao futura (#84). Bases compartilhadas extraidas por evidencia concreta: `SearchBase` (25 ocorrencias de `pesquisa`/`paginas`), `DataJulgamentoMixin` (13 tribunais), `DataPublicacaoMixin` (11), `CnjInputBase`/`OutputCnjConsultaBase` para endpoints de consulta processual (`cpopg`/`cposg`/JusBR). Testes de cobertura (`tests/schemas/test_schema_coverage.py`) garantem que todo metodo publico nao-stub tem schema mapeado; teste de paridade (`tests/schemas/test_signature_parity.py`) garante que os campos do schema batem com a assinatura do metodo mesmo sem wiring. Politica de manutencao documentada em `CLAUDE.md` ("Schemas pydantic (refs #93)"). Outputs marcados como `"Provisorio — revisar quando samples forem capturados (refs #113)"` onde nao ha sample HTML/JSON capturado ainda.
- Schemas pydantic `InputCJSGEsajPuro`/`OutputCJSGEsaj` (em `juscraper.courts._esaj.schemas`) e `InputCJSGTJSP`/`InputCJPGTJSP` (em `juscraper.courts.tjsp.schemas`), com `extra="forbid"`: agora kwargs desconhecidos nos metodos publicos `cjsg`/`cjpg` da familia eSAJ levantam `ValidationError` em vez de serem silenciosamente ignorados. Retrocompat com aliases deprecados (`query`/`termo`, `data_inicio`/`data_fim`, `data_julgamento_de`/`_ate`, `data_publicacao_de`/`_ate`) mantida via `normalize_pesquisa`/`normalize_datas`, que popam os aliases antes da validacao pydantic. Primeira fatia da #93 entregue junto com a POC do #84.
- Suite de testes ampliada para a familia eSAJ: `tests/test_cjsg_schemas.py` valida os schemas pydantic (14 testes); `tests/<sigla>/test_cjsg_filters_contract.py` em TJAC/TJAL/TJAM/TJCE/TJMS/TJSP + `tests/tjsp/test_cjpg_filters_contract.py` exercitam a propagacao de todos os filtros do metodo publico ate o body/query do request (16 testes), via `urlencoded_params_matcher`/`query_param_matcher`. Antes, contratos so cobriam o happy path sem filtros; agora a refatoracao fica protegida contra quebras silenciosas de qualquer filtro. `make_esaj_body` em `tests/fixtures/capture/_util.py` aceita todos os campos do form eSAJ. Refs #84 #93 #104 (gap reportado no comentario da POC).
- Cobertura adicional do caminho compartilhado `EsajSearchScraper.cjsg_download` para aliases deprecados: `tests/tjac/test_cjsg_filters_contract.py` ganha `test_cjsg_query_alias_emits_deprecation_warning` (exerce `normalize_pesquisa` no caminho do super, que os testes do TJSP nao cobrem porque o override popa os aliases antes de delegar) e `test_cjsg_data_inicio_alias_maps_to_data_julgamento` (confirma que `data_inicio`/`data_fim` sao mapeados para `data_julgamento_*` pelo `normalize_datas` antes do pydantic, com `DeprecationWarning` e body canonico no wire). Refs #115.
- Contratos de teste offline para TJSP nos 4 metodos publicos (`cjsg`, `cjpg`, `cpopg` e `cposg`), incluindo variantes `method='html'` e `method='api'` de `cpopg` e `cposg`. Samples capturados via `tests/fixtures/capture/tjsp.py`, cobrindo desde o POST `cjsg/resultadoCompleta.do` ate o fluxo API `search/numproc` → `dadosbasicos` → componentes. Contratos validam schema minimo do DataFrame + payload enviado (via `urlencoded_params_matcher`/`query_param_matcher`). Inclui regressao para o guard `QueryTooLongError` (pesquisa > 120 chars) no `cjsg` e `cjpg`. Segunda fatia da Fase 1 da politica de testes (refs #19, #104).
- Secao "Contrato ao adicionar um novo raspador" em `CLAUDE.md`: checklist obrigatoria de 8 itens (script de captura, samples commitados, matchers, schema via subset, etc.) para todo PR que introduz um raspador novo (refs #104).
- Helpers em `tests/fixtures/capture/_util.py`: `make_tjsp_cjsg_body`, `make_tjsp_cjpg_params`, `TJSP_CHROME_HEADERS`, mais parametros `body_builder`/`headers` em `fetch_cjsg_pages`/`capture_cjsg_samples`. `samples_dir_for` agora aceita `endpoint` alem de `cjsg`. Permite compartilhar logica de captura entre eSAJ-puros e TJSP sem duplicacao.
- Contratos de teste offline para TJAC, TJAL, TJAM, TJCE e TJMS (`cjsg`). Cada tribunal ganhou `tests/<sigla>/test_cjsg_contract.py` cobrindo 3 cenarios (typical com paginacao, pagina unica, sem resultados), alimentados por samples HTML versionados em `tests/<sigla>/samples/cjsg/` e capturados via scripts em `tests/fixtures/capture/<sigla>.py`. Inclui teste de regressao para o adapter TLS `SECLEVEL=1` do TJCE. Primeira fatia da Fase 1 da politica de testes (refs #19, #104).
- TJSP CJPG/CJSG: validacao de tamanho do campo `pesquisa` antes da requisicao. O backend do eSAJ trunca strings com mais de 120 caracteres silenciosamente; agora `cjpg_download` e `cjsg_download` levantam `QueryTooLongError` (subclasse de `ValueError`) quando o limite e excedido. Refs #35.

### Changed

- Familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`) consolidada numa classe compartilhada `juscraper.courts._esaj.EsajSearchScraper`. Os 5 eSAJ-puros viraram clients de ~15 linhas cada (definem so `BASE_URL` e `TRIBUNAL_NAME`); TJCE adicionalmente sobrescreve o hook `_configure_session` para montar o TLS adapter `SECLEVEL=1`; TJSP sobrescreve `_build_cjsg_body` (body diferente), liga o hook de `conversationId` + UA Chrome, e mantem cjpg/cpopg/cposg nos proprios modulos. `QueryTooLongError` do TJSP migrada para `juscraper.courts.tjsp.exceptions`. Saldo: ~2500 linhas removidas em `src/juscraper/courts/`. Dependencia nova: `pydantic>=2.0.0`. API publica preservada byte-a-byte; todos os contratos pre-existentes passam sem alteracao. POC do #84 aplicada a familia 1A (refs #84, #93, #104).
- Samples do TJSP migrados de `tests/tjsp/samples/*.html` (flat) para `tests/tjsp/samples/<endpoint>/*.html` (subdir), alinhando com a convencao introduzida em #102. Arquivos movidos via `git mv`: `cjsg_results.html` → `cjsg/results_normal.html`, `cjsg_single_result.html` → `cjsg/single_result.html`, `cjsg_no_results.html` → `cjsg/no_results.html`, `cjpg_results.html` → `cjpg/results_legacy.html`, `cjpg_results_novo_formato.html` → `cjpg/results_novo_formato.html`, `cpopg_standard.html` → `cpopg/show_standard.html`, `cpopg_alternative.html` → `cpopg/show_alternative.html`. Testes atualizados para consumir os novos caminhos via `tests._helpers.load_sample`; `tests/tjsp/test_utils.py::load_sample_html` e `get_test_samples_dir` removidos (substituidos pelo helper central). `create_mock_response`/`create_mock_session_with_responses` mantidos.
- eSAJ: `juscraper.utils.params.validate_intervalo_datas` aceita parametro `origem` (default `"O eSAJ"`) para reuso em tribunais nao-eSAJ com mensagem de erro correta. Janela maxima default aumentada de 365 para 366 dias para nao rejeitar cliente-side uma janela de 1 ano calendario que atravesse 29/02 (ex: `01/01/2024` -> `01/01/2025`).
- `tests/tjsp/`: removidos hacks de `sys.path.insert` e `from src.juscraper`. Os testes agora dependem do install editavel (`uv pip install -e ".[dev]"`), conforme o `CLAUDE.md` (refs #88).
- **BREAKING:** DataJud `listar_processos` agora levanta `ValueError` em vez de retornar DataFrame vazio quando a sigla do tribunal nao existe nos mappings ou quando nem `tribunal` nem `numero_processo` sao fornecidos. Erros de input do chamador deixam de falhar silenciosamente. Refs #57.
- Dev-tooling: `pyproject.toml` agora inclui `types-requests` e `pytest-mock` nas dev extras e `filterwarnings = ["error"]` na config do pytest. Contribuidores que rodem `pytest`/`mypy` localmente veem o mesmo resultado que o `pre-commit`, sem falsos positivos de stubs ausentes e sem warnings silenciosos.
- `BaseScraper.download_path` passou a ser anotado como `str` (inicializado com `""` e preenchido por `set_download_path` ou pela assinatura da subclasse). `set_download_path` aceita `Optional[str]` explicitamente. Zero impacto em runtime; remove ~15 erros `Optional` em cascata nos clients.
- Politica de testes (Fase 0): `pytest` por default executa apenas testes offline via `addopts = -m 'not integration'`. Para integracao usar `pytest -m integration`; para tudo, `pytest -m ""`. Adicionado `responses` em dev deps (o `pytest-mock` ja havia entrado pelo PR #103); novo marker `vcr` para `pytest-recording`. Criados `tests/conftest.py` (fixture `tests_dir`) e `tests/_helpers.py` (`load_sample`, `load_sample_bytes`). Nova secao "Testes" no `CLAUDE.md` documenta a piramide de testes (contrato/granular/cassete/integracao). Refs #19, #84, #101.

### Removed

- Shim `src/juscraper/courts/tjsp/cjsg_download.py` (apenas compatibility bridge para testes legados que importavam `cjsg_download`/`QueryTooLongError`). Testes em `tests/tjsp/test_query_validation.py` e `tests/tjsp/test_cjsg_contract.py` atualizados para importar direto de `juscraper.courts.tjsp.exceptions`. A docstring de `src/juscraper/courts/tjsp/forms.py::build_tjsp_cjsg_body` reescrita para documentar as diferencas funcionais reais do body do TJSP vs. eSAJ-puros (sem `conversationId`, sem `dtPublicacao*`, `baixar_sg` mapeia para `origem`).
- `tests/tjsp/test_search_limit.py`: redundante com `tests/tjsp/test_query_validation.py` depois da consolidacao do guard de 120 chars em `validate_pesquisa_length`. Cobertura integral preservada pelo `test_query_validation.py`.

### Fixed

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
