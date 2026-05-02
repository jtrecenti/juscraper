# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Novo agregador `comunica_cnj` (`ComunicaCNJScraper`) para a API publica de Comunicacoes Processuais do CNJ. Metodo publico `listar_comunicacoes(pesquisa, paginas=None, data_disponibilizacao_inicio=None, data_disponibilizacao_fim=None, itens_por_pagina=100)`. Datas aceitam ISO `YYYY-MM-DD` e `DD/MM/YYYY`. Validacao via pydantic com `extra="forbid"`.
- `DatajudScraper.listar_processos` e `contar_processos` ganham filtros novos da API Elasticsearch que nao eram acessiveis antes: `data_ajuizamento_inicio`/`data_ajuizamento_fim`, `tipos_movimentacao` (nomes amigaveis: `decisao`/`sentenca`/`julgamento`/`tutela`/`transito_julgado`), `movimentos_codigo` (codigos TPU), `orgao_julgador` e `query` (override total da query Elasticsearch para `must_not`/`should`/`range`/`wildcard`/`nested`/etc.). O alias generico `data_inicio`/`data_fim` **nao** e aceito — DataJud filtra por ajuizamento, nao julgamento. Refs #49, #176.
- Extra opcional `[tjmg]` em `pyproject.toml` declarando `txtcaptcha>=0.1.0`. Para raspar TJMG ao vivo: `pip install juscraper[tjmg]` (ou `uv pip install -e ".[tjmg]"`). Antes a dep era exigida em runtime mas nao formalizada nos metadados.
- TJSP `cjpg_download` e `cjsg_download` validam tamanho do campo `pesquisa` antes da requisicao: strings com mais de 120 caracteres levantam `QueryTooLongError` (subclasse de `ValueError`, em `juscraper.courts.tjsp.exceptions`) em vez de serem silenciosamente truncadas pelo backend. Refs #35.
- Validacao de input via schemas pydantic com `extra="forbid"` em todos os tribunais com refactor concluido (familia eSAJ TJAC/TJAL/TJAM/TJCE/TJMS/TJSP `cjsg`/`cjpg`; familia 1C-a TJRN/TJPA/TJRO/TJSC/TJPI `cjsg`; TJDFT/TJES/TJBA/TJMT/TJAP/TJRS/TJPB/TJTO `cjsg`; TJTO `cjpg`; TJPR/TJGO/TJRR/TJMG `cjsg`; e DataJud `listar_processos`). Kwargs desconhecidos passam a levantar `TypeError` com sugestao de typo (`(você quis dizer 'data_julgamento_inicio'?)`); filtros com formato invalido viram `ValidationError`. Antes eram silenciosamente ignorados. Refs #93, #117, #120, #125, #152, #165, #183.
- Filtros de data nos endpoints com pydantic wired (mesma lista acima) passam a aceitar **quatro variacoes de string** (`DD/MM/AAAA`, `DD-MM-AAAA`, `AAAA-MM-DD`, `AAAA/MM/DD`) e tambem `datetime.date` / `datetime.datetime`. Antes so `DD/MM/AAAA`. Refs #26, #173.

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

### Known Issues

- Dois tribunais tem o teste de filtro de datas marcado como `xfail` estrito em `test_release_date_filter.py`: **TJAP** (Tucujuris genuinamente nao expoe filtro por data — confirmado na engenharia reversa do site) e **TJRJ** (endpoint legado ASP.NET devolve HTTP 500 ate sem filtros). Ambas sao server-side — nao dependem do cliente.

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
