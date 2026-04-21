# CLAUDE.md

## Visao geral do projeto

juscraper e uma biblioteca Python para raspagem de dados de tribunais brasileiros. Coleta dados de jurisprudencia (acordaos, decisoes) do TJDFT, TJPR, TJRS, TJSP e outros tribunais.

## Arquitetura

- Codigo-fonte em `src/juscraper/`
- Tribunais organizados hierarquicamente: `juscraper.courts.<tribunal>.client` (ex: `juscraper.courts.tjrs.client.TJRSScraper`)
- A factory function publica e `juscraper.scraper()`
- Nomes de classes seguem PEP 8 CamelCase: `TJDFTScraper`, `TJPRScraper`, `TJRSScraper`, `TJSPScraper`

## Desenvolvimento

- Python >= 3.11
- Preferir `uv` como gerenciador de pacotes (ja usado no projeto — ver `uv.lock`)
- Instalar em modo editavel: `uv pip install -e ".[dev]"`
- Nunca usar hacks de `sys.path` nos testes — confiar no install editavel
- Pre-commit hooks configurados (trailing whitespace, isort, pylint, flake8, mypy)
- Comprimento maximo de linha: 120

## Testes

### Estrutura

- Testes ficam em `tests/` com subdiretorios por tribunal (`tests/tjdft/`, `tests/tjpr/`, etc.). Cada subdiretorio precisa ter um `__init__.py` para o pytest descobrir os testes.
- Fixtures HTML/JSON ficam em `tests/<tribunal>/samples/<endpoint>/<cenario>.html` (ex.: `tests/tjsp/samples/cjsg/results_normal.html`).
- Helper compartilhado: `tests/_helpers.py::load_sample(tribunal, relative_path)` retorna o sample como string. Use `load_sample_bytes` quando o parser precisa lidar com encoding sozinho (ex.: eSAJ em latin-1).
- Cassetes do `pytest-recording` (quando usados): `tests/<tribunal>/cassettes/`.

### Piramide de testes

| Camada | Sufixo do arquivo | Marker | Quando construir |
|---|---|---|---|
| **Contrato** — API publica via `responses` + samples | `test_*_contract.py` | nenhum | Antes da refatoracao #84 |
| **Granular** — funcao pura testada direto | `test_*_granular.py` | nenhum | Apos cada fase da #84 |
| **Cassete** — fluxo multi-step com `pytest-recording` | `test_*_cassette.py` | `vcr` | Caso a caso (TJPE, TJRR, JusBR) |
| **Integracao** — scraper contra tribunal real | `test_*_integration.py` | `integration` | Sob demanda |

### Ferramentas

- **`responses`** (getsentry) — padrao para mockar `requests.Session` em testes de contrato. Usar `@responses.activate` ou context manager. Validar payload enviado com matchers (`urlencoded_params_matcher`, `json_params_matcher`).
- **`pytest-mock`** — para mockar `time.sleep`, file I/O, `datetime` etc. via fixture `mocker`. Em testes novos, prefira `mocker.patch(...)` em vez de `from unittest.mock import patch`.
- **`pytest-recording`** (vcr.py) — para fluxos multi-step com estado (ViewState, JWT, sessao crypto). Adocao **caso a caso**, nao universal. Medir peso agregado dos cassetes.
- **`unittest.mock`** — continua disponivel; helpers existentes (`tests/tjsp/test_utils.py`) seguem funcionando ate migrarem oportunisticamente.

### Comandos

- `pytest` — roda contrato + granular (offline, ~0.5s). **Default exclui integracao.**
- `pytest -m integration` — roda so integracao (lento, hit live).
- `pytest -m ""` — roda tudo (offline + integracao).
- `pytest tests/tjsp` — escopo a um tribunal.
- `--strict-markers` esta ativo — todo marker deve ser registrado no `pyproject.toml`.

### Regras para autor de teste

- Toda mudanca em parser HTML/JSON deve incluir/atualizar sample em `tests/<tribunal>/samples/<endpoint>/`.
- Testes de contrato afirmam **schema do DataFrame** (colunas obrigatorias) e, quando relevante, **payload enviado** (matchers do `responses`). Isso protege durante refatoracoes.
- Testes que tocam rede ficam marcados com `@pytest.mark.integration`.
- Cassetes (`pytest-recording`) sao adotados caso a caso; medir peso agregado antes de generalizar (limite indicativo: ~20 MB no repo).

### Convergencia com a refatoracao #84

Antes de refatorar um tribunal pela #84, ele precisa ter contratos passando. A camada de contrato valida so a API publica e sobrevive a mudanca estrutural; serve como rede de seguranca da refatoracao. Granulares vem depois, na estrutura ja refatorada. **TJSP refatora por ultimo** (mais usado, mais complexo).

### Contrato ao adicionar um novo raspador

Todo raspador novo em `src/juscraper/courts/<xx>/` ou `src/juscraper/aggregators/<xx>/` deve entrar acompanhado de **pelo menos um teste de contrato** por metodo publico (`cjsg`, `cjpg`, `cpopg`, `cposg`, `listar_processos`, etc.). O PR fica bloqueado sem isso.

Checklist obrigatoria para o PR que adiciona o raspador:

1. **Script de captura** em `tests/fixtures/capture/<xx>.py` que exercita o scraper real e salva as respostas cruas em `tests/<xx>/samples/<endpoint>/<cenario>.<ext>`. Minimo de 3 cenarios por endpoint: typical, sem resultados, pagina unica.
2. **Samples commitados** em `tests/<xx>/samples/<endpoint>/`. Convencao: `results_normal.html`, `single_page.html`, `no_results.html`, `results_normal_page_NN.html` para multi-pagina.
3. **Teste de contrato** em `tests/<xx>/test_<endpoint>_contract.py` seguindo o padrao:
   - `@responses.activate` decorator.
   - `mocker.patch("time.sleep")` em toda funcao/classe com paginacao.
   - `responses.add(..., body=load_sample_bytes("<xx>", "<endpoint>/<cenario>.<ext>"))` para cada request esperado.
   - Matcher de payload sempre que possivel:
     - `urlencoded_params_matcher(..., allow_blank=True)` para POST form (eSAJ manda campos vazios).
     - `json_params_matcher(...)` para POST JSON/GraphQL.
     - `query_param_matcher(...)` para GETs. Filtrar `None` antes de passar (requests remove Nones do URL).
   - Assertiva de schema via **subset**: `{"col_a", "col_b"} <= set(df.columns)`. Nunca igualdade.
   - Pelo menos 3 cenarios: typical, empty (quando o parser aceita), edge (paginacao).
4. **Sem `@pytest.mark.integration`** no contrato.
5. **Sem dependencia de rede, relogio ou TLS real**. Adapter TLS custom: testar so montagem (`isinstance`).
6. **Fluxos multi-step com ordem obrigatoria** usam `responses.registries.OrderedRegistry`.
7. **Captchas, tokens dinamicos e libs externas** (`txtcaptcha`, `browser_cookie3`) sao **mockados** — nunca invocados. Injetar fakes via `mocker.patch.dict(sys.modules, ...)` para lazy imports ausentes das deps.
8. **Entry no CHANGELOG** em `[Unreleased]/Added`.

## Convencao de API para raspadores

- Busca: `pesquisa` como nome padrao em todos os scrapers
- Datas: `data_julgamento_inicio/fim`, `data_publicacao_inicio/fim`
- Alias generico: `data_inicio/fim` mapeia para `data_julgamento_inicio/fim`
- Nomes antigos (`query`, `termo`, `_de/_ate`) aceitos com DeprecationWarning
- Paginacao: `paginas: int | list | range | None`, default `None` (todas as paginas)
- `paginas` e sempre 1-based: range(1, 4) baixa paginas 1, 2 e 3; paginas=3 e equivalente a range(1, 4)
- Normalizacao centralizada em `src/juscraper/utils/params.py`

## Extracao de numero de paginas/resultados em raspadores HTML

Paginas de tribunais mudam estrutura sem aviso. Ao escrever logica que extrai contagem de resultados ou numero de paginas a partir de HTML:

- Use selecao em cascata (varios seletores tentados em sequencia), nao um unico seletor fragil como `bgcolor` ou class especifica.
- Use regex em cascata, nao um unico regex que assume o texto exato. Padrao recomendado: tentar `\d+$` (numero no final), depois `(?<=de )[0-9]+` (numero apos "de"), depois capturas com descritores opcionais (`resultado`, `registro`, `pagina`), e como ultimo recurso pegar o maior `\d+` do texto.
- Referencia canonica no projeto: `cjsg_n_pags` em `src/juscraper/courts/tjsp/cjsg_parse.py` e `cjpg_n_pags` em `src/juscraper/courts/tjsp/cjpg_parse.py`.
- Quando um regex novo for adicionado, salvar um sample HTML em `tests/<tribunal>/samples/` cobrindo cada formato suportado (antigo e novo) e ter um teste unitario por formato.

## Regras de workflow no GitHub

- Nunca tentar aprovar o proprio PR (`gh pr review --approve` falha para o autor do PR)
- Usar `gh pr review --comment` para deixar notas de revisao nos proprios PRs
- Sempre fazer push para uma branch de feature e abrir PR — nunca fazer push direto na main
- **Merge de PRs: sempre usar commit de merge (`gh pr merge <n> --merge --delete-branch`)**, nunca squash nem rebase. O commit de merge preserva cada commit individual da branch *e* adiciona um commit `Merge pull request #<n> from <branch>` que marca o limite do PR — ou seja, `git log --all --graph` continua mostrando o que entrou em cada PR. Squash perde a granularidade dos commits; rebase perde o limite do PR. Deletar a branch remota no merge mantem a lista de branches do repo enxuta (a branch continua acessivel via `gh pr checkout <n>`).

## Changelog

- Seguimos o padrao [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- Toda mudanca relevante deve ser registrada em `CHANGELOG.md` sob `[Unreleased]`
- Categorias: Added, Changed, Deprecated, Removed, Fixed, Security
- **Secoes de versoes ja lancadas (`## [0.2.1]`, `## [0.2.0]`, ...) sao imutaveis.** Nunca adicionar, editar ou remover linhas dentro delas — elas descrevem o que foi publicado naquela tag. Toda entrada nova vai em `[Unreleased]`, mesmo que corrija algo introduzido na ultima versao.
- **Antes de inserir uma entrada, confirme que ela cai *acima* do primeiro heading `## [x.y.z]` do arquivo** (ou seja, dentro de `[Unreleased]`). Se `[Unreleased]` estiver sem subsecoes (`### Added/Changed/Fixed/...`), crie a subsecao necessaria.
- **Todo commit de `feat:`, `fix:`, `refactor:` ou `deprecated:` com efeito observavel pelo usuario deve incluir a entrada em `[Unreleased]` no mesmo commit** — nao em commit posterior. Mudancas puramente internas (testes, tipagem, rename de simbolo privado, docs) nao precisam.

## Documentacao

- Documentacao do projeto (em `docs/`) deve ser escrita em ingles
- Portugues causa problemas de encoding no build do site (Quarto + GitHub Actions)
