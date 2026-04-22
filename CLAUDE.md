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
4. **Pydantic schema** em `src/juscraper/courts/<xx>/schemas.py` (ou no diretorio compartilhado `src/juscraper/courts/_<familia>/schemas.py`) com `model_config = ConfigDict(extra="forbid")`. Um modelo por endpoint (`InputCJSG<TRIB>`, `InputCJPG<TRIB>`, etc.), herdando de `juscraper.schemas.cjsg.SearchBase`. O modelo **e a fonte unica da verdade da API publica** — params listados no scraper tem que bater com campos do modelo.
5. **Teste de schema** em `tests/<xx>/test_<endpoint>_schema_contract.py` (ou consolidado em `tests/test_cjsg_schemas.py` para modelos compartilhados): valida (a) todos os params documentados aceitos, (b) kwargs desconhecidos levantam `ValidationError`, (c) defaults corretos, (d) validators/Literals rejeitam valores fora do dominio.
6. **Teste de propagacao de filtros** em `tests/<xx>/test_<endpoint>_filters_contract.py`: chama o metodo publico passando **todos** os filtros simultaneamente e o matcher (`urlencoded_params_matcher`/`json_params_matcher`/`query_param_matcher`) confirma que cada filtro chegou no body/params. Fecha o gap onde o happy-path com filtros vazios nao detecta uma quebra de propagacao.
7. **Sem `@pytest.mark.integration`** no contrato.
8. **Sem dependencia de rede, relogio ou TLS real**. Adapter TLS custom: testar so montagem (`isinstance`).
9. **Fluxos multi-step com ordem obrigatoria** usam `responses.registries.OrderedRegistry`.
10. **Captchas, tokens dinamicos e libs externas** (`txtcaptcha`, `browser_cookie3`) sao **mockados** — nunca invocados. Injetar fakes via `mocker.patch.dict(sys.modules, ...)` para lazy imports ausentes das deps.
11. **Entry no CHANGELOG** em `[Unreleased]/Added`.

## Convencao de API para raspadores

- Busca: `pesquisa` como nome padrao em todos os scrapers
- Datas: `data_julgamento_inicio/fim`, `data_publicacao_inicio/fim`
- Alias generico: `data_inicio/fim` mapeia para `data_julgamento_inicio/fim`
- Nomes antigos (`query`, `termo`, `_de/_ate`) aceitos com DeprecationWarning
- Paginacao: `paginas: int | list | range | None`, default `None` (todas as paginas)
- `paginas` e sempre 1-based: range(1, 4) baixa paginas 1, 2 e 3; paginas=3 e equivalente a range(1, 4)
- Normalizacao centralizada em `src/juscraper/utils/params.py`
- **Validacao da API publica via pydantic com `extra="forbid"`** (ver secao "Schemas pydantic" abaixo). Kwargs desconhecidos levantam `ValidationError` em vez de serem silenciosamente ignorados.

## Schemas pydantic (refs #93)

Todo endpoint publico de raspador (`cjsg`, `cjpg`, `cpopg`, `cposg`, `listar_processos`, ...) e validado por um modelo pydantic antes de chegar nos internals. Isso:

- Documenta a API publica de forma executavel (`InputCJSGTJSP.model_json_schema()` gera o schema JSON).
- Rejeita kwargs desconhecidos (`extra="forbid"`), que antes eram silenciosamente ignorados.
- Resolve automaticamente a #68 (singular/plural): o nome do campo na classe pydantic e a decisao unica.
- Substitui `validate_*` espalhados pelos scrapers por um so ponto de verdade.

### Onde ficam os modelos

- `src/juscraper/schemas/cjsg.py` — modelos compartilhados: `SearchBase` (pesquisa + paginas + datas, com `extra="forbid"` e `arbitrary_types_allowed=True` para `range`), `OutputCJSGBase` (colunas minimas de todo cjsg).
- `src/juscraper/courts/_<familia>/schemas.py` — modelos compartilhados pela familia (ex.: `InputCJSGEsajPuro` para 5 tribunais eSAJ-puros).
- `src/juscraper/courts/<xx>/schemas.py` — modelo especifico do tribunal quando diverge da familia (ex.: `InputCJSGTJSP` usa `baixar_sg: bool` em vez de `origem: Literal["T","R"]`).

### Regras de desenho

- Modelos de endpoints diferentes sao **irmaos** de `SearchBase`, nao herdam entre si (ex.: `InputCJSGEsajPuro` e `InputCJSGTJSP` nao compartilham herdanca porque a API publica divergiu historicamente).
- Campos listados **tem que bater byte-a-byte** com a assinatura do metodo publico. Adicionar um filtro novo no pydantic sem adicionar no metodo (e vice-versa) e bug.
- Validators que levantam excecoes custom (ex.: `QueryTooLongError`) **rodam no scraper antes do pydantic**, nao no validator pydantic — senao a excecao vira wrapped em `ValidationError`. Padrao: `validate_pesquisa_length(pesquisa, endpoint="CJSG")` logo no topo do metodo publico.
- Retrocompat com aliases deprecados (`query`/`termo`, `data_inicio`/`data_fim`, `data_*_de`/`_ate`) e tratada **antes** do pydantic via `normalize_pesquisa`/`normalize_datas` em `src/juscraper/utils/params.py`, que popam os aliases emitindo `DeprecationWarning`. O que sobrar em `kwargs` cai no pydantic e e rejeitado.
- `_raise_on_extra(exc, method_name)` em `juscraper.courts._esaj.base` converte `ValidationError` de `extra_forbidden` em `TypeError` amigavel (`"got unexpected keyword argument"`).

## Raspadores eSAJ: como adicionar um novo tribunal

A familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP) compartilha a infra em `src/juscraper/courts/_esaj/`. Para adicionar um novo tribunal eSAJ:

### 1. Caso tipico (5 eSAJ-puros) — ~8 linhas

```python
# src/juscraper/courts/tjXX/client.py
from .._esaj.base import EsajSearchScraper

class TJXXScraper(EsajSearchScraper):
    BASE_URL = "https://esaj.tjXX.jus.br/"
    TRIBUNAL_NAME = "TJXX"
```

O scraper herda `cjsg`, `cjsg_download`, `cjsg_parse`, validacao via `InputCJSGEsajPuro`, retry/paginacao/latin-1, e `OutputCJSGEsaj`.

### 2. Customizacao pontual (TJCE — TLS)

```python
class TJXXScraper(EsajSearchScraper):
    BASE_URL = "..."
    TRIBUNAL_NAME = "..."

    def _configure_session(self, session: requests.Session) -> None:
        session.mount("https://", CustomTLSAdapter())
```

### 3. API divergente (TJSP)

```python
class TJXXScraper(EsajSearchScraper):
    BASE_URL = "..."
    TRIBUNAL_NAME = "..."
    INPUT_CJSG = InputCJSGTJXX        # pydantic proprio quando a API diverge
    CJSG_CHROME_UA = True              # quando o eSAJ precisa de UA browser
    CJSG_EXTRACT_CONVERSATION_ID = True  # quando precisa propagar conversationId entre paginas

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        # sobrescrever quando o form body tem shape diferente
        ...
```

### 4. Hooks disponiveis

- `_configure_session(session)` — montar adapters HTTP customizados (TLS, cookies, etc.)
- Atributos de classe `CJSG_CHROME_UA`, `CJSG_EXTRACT_CONVERSATION_ID` (defaults `False`)
- `_build_cjsg_body(inp)` — trocar o builder do form body quando diverge do default `build_cjsg_form_body`

**Nao adicionar `if tribunal == "X"` no codigo compartilhado.** Se a particularidade nao encaixar via hook/atributo, prefira um scraper proprio fora da familia em vez de vazar a diferenca na base.

### 5. Quando generalizar algo para `_esaj/` (regra de promocao sob demanda)

Particularidades de tribunal (validators, excecoes, helpers de form, limites constantes) ficam em `src/juscraper/courts/<xx>/` **enquanto so um tribunal da familia precisar delas**. Generalizar para `_esaj/` (ou equivalente da familia) so quando o **segundo** caso concreto aparecer — nao preemptivamente. Exemplo: `QueryTooLongError` e `validate_pesquisa_length(pesquisa, endpoint)` vivem em `src/juscraper/courts/tjsp/exceptions.py` porque so TJSP tem limite de 120 chars; quando o segundo tribunal eSAJ precisar de validator analogo (com seu proprio `max_chars`), mover para `src/juscraper/courts/_esaj/exceptions.py` parametrizando o que diverge (`max_chars=120` default ou sem default), e atualizar todos os imports.

Motivos:

- Duplicacao de 1 tribunal e baixo custo; abstracao errada e alto custo (forca refactor em cascata quando o segundo caso nao se encaixa).
- A forma certa da abstracao so fica clara **depois** de ver o segundo caso — generalizar com 1 exemplo so chuta o desenho.
- Mantem `_esaj/` enxuto e focado no que e de fato compartilhado.

Vale para qualquer nova particularidade ao longo do refactor #84 nas familias 1B/1C/1D.

### 6. O que nao e eSAJ

Familias 1B (APIs JSON/GraphQL), 1C (HTML/Session), 1D (agregadores) nao reusam `EsajSearchScraper`. A analogia, se aplicada: cada familia ganha sua propria infra compartilhada (`_api/`, `_session/`, ...) seguindo o mesmo padrao (base class + pydantic schemas compartilhados + hooks para casos de borda).

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
