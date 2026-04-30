# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit
helps, and credit will always be given.

## Types of Contributions

### Report Bugs

If you are reporting a bug, please include:

* Your operating system name and version.
* Any details about your local setup that might be helpful in troubleshooting.
* Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help
wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement"
and "help wanted" is open to whoever wants to implement it.

### Write Documentation

You can never have enough documentation! Please feel free to contribute to any
part of the documentation, such as the official docs, docstrings, or even
on the web in blog posts, articles, and such.

### Submit Feedback

If you are proposing a feature:

* Explain in detail how it would work.
* Keep the scope as narrow as possible, to make it easier to implement.
* Remember that this is a volunteer-driven project, and that contributions
  are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `juscraper` for local development.

1. Download a copy of `juscraper` locally.
2. Install `juscraper` using `poetry`:

    ```console
    $ poetry install
    ```

3. Use `git` (or similar) to create a branch for local development and make your changes:

    ```console
    $ git checkout -b name-of-your-bugfix-or-feature
    ```

4. When you're done making changes, check that your changes conform to any code formatting requirements and pass any tests.

5. Commit your changes and open a pull request.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include additional tests if appropriate.
2. If the pull request adds functionality, the docs should be updated.
3. The pull request should work for all currently supported operating systems and versions of Python.

## Code of Conduct

Please note that the `juscraper` project is released with a
Code of Conduct. By contributing to this project you agree to abide by its terms.

---

# Internal Dev Guide

As seções a seguir são notas internas para quem contribui com novos raspadores, schemas ou refatorações. Estão em português para acompanhar o conteúdo original do `CLAUDE.md`. Termos técnicos do projeto (`pesquisa`, `paginas`, `data_julgamento_*`, etc.) ficam no original.

## Tests

### Pirâmide de testes

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

### Convergência com a refatoração #84

Antes de refatorar um tribunal pela #84, ele precisa ter contratos passando. A camada de contrato valida só a API pública e sobrevive à mudança estrutural; serve como rede de segurança da refatoração. Granulares vêm depois, na estrutura já refatorada. **TJSP refatora por último** (mais usado, mais complexo).

## Adding a new tribunal

Todo raspador novo em `src/juscraper/courts/<xx>/` ou `src/juscraper/aggregators/<xx>/` deve entrar acompanhado de **pelo menos um teste de contrato** por método público (`cjsg`, `cjpg`, `cpopg`, `cposg`, `listar_processos`, etc.). O PR fica bloqueado sem isso.

Checklist obrigatória para o PR que adiciona o raspador:

1. **Script de captura** em `tests/fixtures/capture/<xx>.py` que **sempre** exercita o scraper contra o backend real do tribunal e salva as respostas cruas em `tests/<xx>/samples/<endpoint>/<cenario>.<ext>`. Nunca sintetizar samples a mão — o shape do backend é a fonte da verdade do contrato, não adivinhação. Se o backend estiver indisponível no momento, documentar e abrir issue separada em vez de mockar campos. Mínimo de 3 cenários por endpoint: typical, sem resultados, página única. Saneamento pós-captura (truncar Base64, remover highlights de Elasticsearch, etc.) é OK e fica dentro do próprio script — ver `tests/fixtures/capture/tjrs.py` como referência.
2. **Samples commitados** em `tests/<xx>/samples/<endpoint>/`. Convenção: `results_normal.html`, `single_page.html`, `no_results.html`, `results_normal_page_NN.html` para multi-página.
3. **Teste de contrato** em `tests/<xx>/test_<endpoint>_contract.py` seguindo o padrão:
   - `@responses.activate` decorator.
   - `mocker.patch("time.sleep")` em toda função/classe com paginação.
   - `responses.add(..., body=load_sample_bytes("<xx>", "<endpoint>/<cenario>.<ext>"))` para cada request esperado.
   - Matcher de payload sempre que possível:
     - `urlencoded_params_matcher(..., allow_blank=True)` para POST form (eSAJ manda campos vazios).
     - `json_params_matcher(...)` para POST JSON/GraphQL.
     - `query_param_matcher(...)` para GETs. Filtrar `None` antes de passar (requests remove Nones do URL).
   - Assertiva de schema via **subset**: `{"col_a", "col_b"} <= set(df.columns)`. Nunca igualdade.
   - Pelo menos 3 cenários: typical, empty (quando o parser aceita), edge (paginação).
4. **Pydantic schema** em `src/juscraper/courts/<xx>/schemas.py` (ou no diretório compartilhado `src/juscraper/courts/_<familia>/schemas.py`) com `model_config = ConfigDict(extra="forbid")`. Um modelo por endpoint (`InputCJSG<TRIB>`, `InputCJPG<TRIB>`, etc.), herdando de `juscraper.schemas.cjsg.SearchBase`. O modelo **é a fonte única da verdade da API pública** — params listados no scraper têm que bater com campos do modelo.
5. **Teste de schema** em `tests/<xx>/test_<endpoint>_schema_contract.py` (ou consolidado em `tests/test_cjsg_schemas.py` para modelos compartilhados): valida (a) todos os params documentados aceitos, (b) kwargs desconhecidos levantam `ValidationError`, (c) defaults corretos, (d) validators/Literals rejeitam valores fora do domínio.
6. **Teste de propagação de filtros** em `tests/<xx>/test_<endpoint>_filters_contract.py`: chama o método público passando **todos** os filtros simultaneamente e o matcher (`urlencoded_params_matcher`/`json_params_matcher`/`query_param_matcher`) confirma que cada filtro chegou no body/params. Fecha o gap onde o happy-path com filtros vazios não detecta uma quebra de propagação.
6a. **Cobertura mínima de aliases deprecados** no `test_<endpoint>_filters_contract.py`: um teste para **cada** alias que o scraper aceita em `normalize_pesquisa`/`normalize_datas`, assertando o `DeprecationWarning` + (quando aplicável) que o valor cai no body/params como o canônico. Exemplos: `query`/`termo` se o endpoint tem busca textual; `data_inicio`/`data_fim` se o endpoint tem filtro de data. Quando o alias vira noop silencioso (ex.: `data_inicio` num tribunal que só suporta `data_publicacao`), testar que o `DeprecationWarning` + o `UserWarning` de `warn_unsupported` são emitidos juntos.
7. **Sem `@pytest.mark.integration`** no contrato.
8. **Sem dependência de rede, relógio ou TLS real**. Adapter TLS custom: testar só montagem (`isinstance`).
9. **Fluxos multi-step com ordem obrigatória** usam `responses.registries.OrderedRegistry`.
10. **Captchas, tokens dinâmicos e libs externas** (`txtcaptcha`, `browser_cookie3`) são **mockados** — nunca invocados. Injetar fakes via `mocker.patch.dict(sys.modules, ...)` para lazy imports ausentes das deps.
11. **Entry no CHANGELOG** em `[Unreleased]/Added`.
12. **Payload builders públicos** em `courts/<xx>/download.py` sempre que o script de captura precisar reusar o dict/body enviado ao backend. Extrair como função de nome público (`build_<endpoint>_payload` — **sem underscore inicial**) + constante da URL base (`BASE_URL`, `RESULTS_PER_PAGE`, etc.). O script em `tests/fixtures/capture/<xx>.py` importa esses helpers em vez de redefinir o payload inline — qualquer mudança no scraper quebra a captura, evitando drift silencioso. Helpers privados (`_`) em módulos de download ficam reservados para lógica interna não reusada pelo capture script.

## Schemas pydantic

### Onde ficam os modelos

- `src/juscraper/schemas/cjsg.py` — `SearchBase` (pesquisa, paginas: **1-based, contrato único**) e `OutputCJSGBase` (processo, ementa?, data_julgamento?). Sem filtros de data na base.
- `src/juscraper/schemas/mixins.py` — Input: `DataJulgamentoMixin`, `DataPublicacaoMixin`. Output: `OutputRelatoriaMixin` (relator, orgao_julgador), `OutputDataPublicacaoMixin` (data_publicacao). Tribunal herda se aplicável; quem não suporta deixa `extra="forbid"` rejeitar.
- `src/juscraper/schemas/consulta.py` — `CnjInputBase` (`id_cnj: str | list[str]`), `OutputCnjConsultaBase` para cpopg/cposg/JusBR.
- `src/juscraper/courts/_<familia>/schemas.py` — compartilhado pela família (ex.: `InputCJSGEsajPuro`, `OutputCJSGEsaj`). Criar só com 2+ ocorrências (Regra 1 do #84).
- `src/juscraper/courts/<xx>/schemas.py` / `aggregators/<yy>/schemas.py` — um arquivo por tribunal/agregador com Input/Output de todos os endpoints.

### Pipeline canônico (wiring)

Pipeline implementado em `juscraper.utils.params.apply_input_pipeline_search` (chamado por `src/juscraper/courts/_esaj/base.py:cjsg_download` e `tjsp/client.py:cjpg_download`) e exercitado em `tests/tj{ac,al,am,ce,ms,sp}/test_cjsg_filters_contract.py`. Ao wirar tribunal novo, copiar a ordem de lá: aliases (via `normalize_pesquisa`/`normalize_datas`) → validators custom → pydantic → build body a partir do modelo. Motivos: aliases antes do pydantic (senão viram `TypeError` genérico); validators custom antes (senão viram wrapped em `ValidationError`); `raise_on_extra_kwargs` depois (só `extra_forbidden` deve virar `TypeError` — erro de tipo real sobe natural). Tribunais sem limite documentado de janela ficam com `max_dias=None` (default); eSAJ passa `max_dias=366, origem="O eSAJ"` explicitamente.

### Checklist ao adicionar um tribunal novo

1. Criar `courts/<xx>/schemas.py` com Input+Output para cada método **implementado**.
2. Herdar `SearchBase` + mixins aplicáveis; Output herda `OutputCJSGBase` + `OutputRelatoriaMixin`/`OutputDataPublicacaoMixin` conforme o parser entregue. Campos não-herdados do Output são declarados Optional.
3. Se o parser usa nomes divergentes do canônico (`classe_cnj`, `magistrado`, `nr_processo`, ...), renomear no parser antes de commitar — Output fica com o nome canônico.
4. Registrar em `tests/schemas/test_schema_coverage.py::EXPECTED_COURT_SCHEMAS` **e** `tests/schemas/test_output_parity.py::EXPECTED_COURT_OUTPUT_SCHEMAS`, rodar `pytest tests/schemas/`.
5. Se já refatorado, wirar o schema no método público seguindo o pipeline canônico de `_esaj/base.py`.

## Adding an eSAJ tribunal

A família eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP) compartilha a infra em `src/juscraper/courts/_esaj/`. Para adicionar um novo tribunal eSAJ:

### 1. Caso típico (5 eSAJ-puros) — ~8 linhas

```python
# src/juscraper/courts/tjXX/client.py
from .._esaj.base import EsajSearchScraper

class TJXXScraper(EsajSearchScraper):
    BASE_URL = "https://esaj.tjXX.jus.br/"
    TRIBUNAL_NAME = "TJXX"
```

O scraper herda `cjsg`, `cjsg_download`, `cjsg_parse`, validação via `InputCJSGEsajPuro`, retry/paginação/latin-1, e `OutputCJSGEsaj`.

### 2. Customização pontual (TJCE — TLS)

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
    INPUT_CJSG = InputCJSGTJXX        # pydantic próprio quando a API diverge
    CJSG_CHROME_UA = True              # quando o eSAJ precisa de UA browser
    CJSG_EXTRACT_CONVERSATION_ID = True  # quando precisa propagar conversationId entre páginas

    def _build_cjsg_body(self, inp: BaseModel) -> dict:
        # sobrescrever quando o form body tem shape diferente
        ...
```

### 4. Hooks disponíveis

- `_configure_session(session)` — montar adapters HTTP customizados (TLS, cookies, etc.)
- Atributos de classe `CJSG_CHROME_UA`, `CJSG_EXTRACT_CONVERSATION_ID` (defaults `False`)
- `_build_cjsg_body(inp)` — trocar o builder do form body quando diverge do default `build_cjsg_form_body`

**Não adicionar `if tribunal == "X"` no código compartilhado.** Se a particularidade não encaixar via hook/atributo, prefira um scraper próprio fora da família em vez de vazar a diferença na base.

### 5. Quando generalizar algo para `_esaj/` (regra de promoção sob demanda)

Particularidades de tribunal (validators, exceções, helpers de form, limites constantes) ficam em `src/juscraper/courts/<xx>/` **enquanto só um tribunal da família precisar delas**. Generalizar para `_esaj/` (ou equivalente da família) só quando o **segundo** caso concreto aparecer — não preemptivamente. Exemplo: `QueryTooLongError` e `validate_pesquisa_length(pesquisa, endpoint)` vivem em `src/juscraper/courts/tjsp/exceptions.py` porque só TJSP tem limite de 120 chars; quando o segundo tribunal eSAJ precisar de validator análogo (com seu próprio `max_chars`), mover para `src/juscraper/courts/_esaj/exceptions.py` parametrizando o que diverge (`max_chars=120` default ou sem default), e atualizar todos os imports.

Motivos:

- Duplicação de 1 tribunal é baixo custo; abstração errada é alto custo (força refactor em cascata quando o segundo caso não se encaixa).
- A forma certa da abstração só fica clara **depois** de ver o segundo caso — generalizar com 1 exemplo só chuta o desenho.
- Mantém `_esaj/` enxuto e focado no que é de fato compartilhado.

Vale para qualquer nova particularidade ao longo do refactor #84 nas famílias 1B/1C/1D.
