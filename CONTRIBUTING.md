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
2. Install the editable package and development dependencies with `uv`:

    ```console
    $ uv sync --extra dev
    ```

3. Work on a feature branch in a dedicated worktree, reusing it if the session already provides one. Follow `CLAUDE.md` > **Worktree e GitHub** for isolation and cleanup.

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

### Estrutura e samples

- Organizar testes em `tests/<tribunal>/`, com `__init__.py` para manter os módulos de tribunais distintos como pacotes.
- Guardar respostas reais em `tests/<tribunal>/samples/<endpoint>/<cenario>.<ext>`. Toda mudança no parser exige sample e teste do formato afetado; o procedimento de captura está em **Adding a new tribunal**.
- Carregar samples com `tests/_helpers.py::load_sample`; usar `load_sample_bytes` quando o parser deve tratar o encoding, como no eSAJ em latin-1.
- Contratos verificam colunas obrigatórias do DataFrame por subset e o payload enviado por matchers. Marcar testes que acessam rede com `integration`; registrar novos markers em `pyproject.toml`, pois `--strict-markers` está ativo.

`uv run pytest` exclui integração por padrão. Para executar todas as camadas, inclusive rede, usar `uv run pytest -m ""`.

### Pirâmide de testes

| Camada | Sufixo do arquivo | Marker | Quando construir |
|---|---|---|---|
| **Contrato** — API publica via `responses` + samples | `test_*_contract.py` | nenhum | Antes da refatoracao #84 |
| **Granular** — funcao pura testada direto | `test_*_granular.py` | nenhum | Apos cada fase da #84 |
| **Cassete** — fluxo multi-step com `pytest-recording` | `test_*_cassette.py` | `vcr` | Caso a caso (TJPE, TJRR, JusBR) |
| **Integracao** — scraper contra tribunal real | `test_*_integration.py` | `integration` | Sob demanda |

### Marker `anti_bot` — bloqueio anti-bot esperado (refs #292)

A consulta pública PJe de TRF1, TRF3 e TRF5 fica atrás do bot manager Akamai. De IPs de datacenter/CI o portal devolve `HTTP 403 Access Denied` e o scraper levanta `BotChallengeBlockedError` de propósito (bloqueio session-wide). Isso é **falha ambiental** — depende do IP do cliente, passa de IP residencial — e não regressão de código. O marker `anti_bot` distingue os dois casos sem esconder regressão real.

O `tests/conftest.py` registra um hook (`pytest_runtest_makereport`, `wrapper=True`) que, **apenas** para testes marcados `anti_bot`, converte `BotChallengeBlockedError` em `xfail`. Qualquer outra exceção — parser quebrado, schema rejeitando input antes válido, coluna renomeada — continua falhando vermelho, e de IP residencial (sem bloqueio) o teste passa normal. Diferente do `xfail(strict=False)` cego de TJAP (Turnstile) e TJRR (PrimeFaces), que são bloqueios *permanentes*: o Akamai é *condicional ao IP*, então o teste só vira xfail quando o bloqueio de fato acontece.

Aplicar com `pytestmark = pytest.mark.anti_bot` no topo do arquivo de integração (cobre todos os testes do arquivo, que batem no mesmo backend protegido). Comandos:

```bash
pytest -m "integration and anti_bot"        # IP residencial: cobertura real dos TRFs
pytest -m "integration and not anti_bot"    # CI/datacenter: pula os anti-bot por completo
pytest -m integration                        # roda tudo; bloqueio Akamai vira xfail, regressao real falha
```

O hook é coberto por `tests/test_anti_bot_marker.py` (offline, via `pytester`), que reusa a implementação real e afirma os três casos: bloqueio+marker → xfail; regressão real → fail; bloqueio sem marker → fail.

### Ferramentas

- **`responses`** (getsentry) — padrao para mockar `requests.Session` em testes de contrato. Usar `@responses.activate` ou context manager. Validar payload enviado com matchers (`urlencoded_params_matcher`, `json_params_matcher`).
- **`pytest-mock`** — para mockar `time.sleep`, file I/O, `datetime` etc. via fixture `mocker`. Em testes novos, prefira `mocker.patch(...)` em vez de `from unittest.mock import patch`.
- **`pytest-recording`** (vcr.py): para fluxos com estado (ViewState, JWT, sessão crypto). Adotar caso a caso e medir o peso agregado antes de generalizar; limite indicativo de 20 MB de cassetes no repositório.
- **`unittest.mock`** — continua disponivel; helpers existentes (`tests/tjsp/test_utils.py`) seguem funcionando ate migrarem oportunisticamente.

### Convergência com a refatoração #84

Antes de refatorar um tribunal pela #84, ele precisa ter contratos passando. A camada de contrato valida só a API pública e sobrevive à mudança estrutural; serve como rede de segurança da refatoração. Granulares vêm depois, na estrutura já refatorada. **TJSP refatora por último** (mais usado, mais complexo).

### Notebooks como sanity check (`pytest --nbmake`)

Os notebooks de exemplo em `docs/notebooks/<tribunal>.ipynb` exercitam o fluxo público de cada raspador (cjsg, cjpg, cpopg, cposg, listar_processos) com chamadas reais ao tribunal. Servem ao mesmo tempo como documentação executável (build do site Quarto) e como **canário de regressão pós-refactor** — pegam quebras visíveis ao usuário (parser quebrado, schema rejeitando input antes válido, coluna renomeada sem migração) que um teste granular pode mascarar. A execução local é o ambiente de referência; compatibilidade com o Google Colab ou outro provedor de notebooks em nuvem não integra os critérios de aceitação do projeto.

Comando padrão (rodar localmente antes de release ou após refactor amplo):

```bash
pytest --nbmake docs/notebooks/ \
  --ignore=docs/notebooks/jusbr.ipynb \
  --ignore=docs/notebooks/tjmg.ipynb \
  --nbmake-timeout=300 \
  -n auto
```

Notas:

- **Não rodar em `pre-commit` nem em CI por PR.** São 25 notebooks contra rede real (~10-30 min com `pytest-xdist`); flakiness de tribunal vai bloquear merge sem motivo. O lugar certo, se um dia entrar no CI, é o workflow nightly proposto em #101 com `continue-on-error`.
- Falhas de conexão no Google Colab ou em outro ambiente de nuvem devem ser reproduzidas localmente antes de motivar mudanças em timeout, retry ou no scraper. Um `ConnectTimeout` sem resposta HTTP pode indicar bloqueio de IP compartilhado ou problema de rota; isoladamente, não demonstra regressão do `juscraper` nem bloqueio intencional pelo tribunal.
- `jusbr.ipynb` é excluído porque depende de token gov.br (`JUSBR_ACCESS_TOKEN`); `tjmg.ipynb` depende do extra `[tjmg]` instalado (`txtcaptcha`). Ambos rodam sob demanda quando as condições estão presentes.
- Falha 5xx em um único notebook normalmente é instabilidade do tribunal — re-rodar o notebook isolado antes de reportar regressão (`pytest --nbmake docs/notebooks/<tribunal>.ipynb`).
- Quando o resultado real divergir do output cacheado (ex.: coluna nova, ementa em formato diferente), o notebook deve ser **commitado com outputs limpos** (`jupyter nbconvert --clear-output --inplace docs/notebooks/<tribunal>.ipynb`) para que `git diff` futuro fique focado em código.

## Complexidade de código (lizard + complexipy)

Complexidade é um eixo que o stack de lint do projeto (Ruff, flake8, isort, pylint, mypy) **não cobre** — esses veem estilo e tipos. Medimos duas métricas **complementares**, porque elas pegam coisas diferentes e divergem na prática (ver tabela abaixo). Ambas entram no extra `[dev]`. Refs #307.

- **Complexidade ciclomática** (`lizard`, métrica CCN): conta caminhos independentes — começa em 1 e soma +1 por ponto de decisão (`if`, `for`, `while`, `except`, `and`, `or`, …). É um proxy de *testabilidade* (quantos casos cobrir). Não conta linhas nem aninhamento.
- **Complexidade cognitiva** (`complexipy`, métrica do SonarSource): conta o quão difícil é *entender* o código, com **penalidade por aninhamento** — um `if` dentro de `for` dentro de `if` custa mais que três `if` rasos.

Por que as duas: elas concordam nos extremos, mas divergem no meio. Código **plano com muitos ramos**, como uma sequência de tentativas encadeadas com `or` ou um `match/case`, é ciclomático-alto mas cognitivo-baixo, e continua legível. Uma cascata de `if/elif` não entra nesse caso: cada `elif` custa +1 nas duas métricas. Código **aninhado com poucos ramos** é o oposto. Os dois exemplos abaixo foram escritos para esta documentação e não vêm do `src`, para que os números não mudem a cada refatoração.

**(a) Plano com muitos ramos**, uma sequência de tentativas no mesmo nível:

```python
import re


def extrair_total_resultados(texto):
    """Tenta, em ordem, os formatos de contagem que cada tribunal usa."""
    achado = (
        re.search(r"(\d+) resultados? encontrados?", texto)
        or re.search(r"Total de registros: (\d+)", texto)
        or re.search(r"Exibindo \d+ a \d+ de (\d+)", texto)
        or re.search(r"Foram encontrados (\d+) documentos", texto)
        or re.search(r"(\d+) acórdãos", texto)
        or re.search(r"(\d+) decisões", texto)
        or re.search(r"Resultados: (\d+)", texto)
        or re.search(r"de um total de (\d+)", texto)
        or re.search(r"Quantidade: (\d+)", texto)
        or re.search(r"(\d+) processos", texto)
        or re.search(r"(\d+) itens", texto)
        or re.search(r"(\d+) registros", texto)
        or re.search(r"(\d+) julgados", texto)
        or re.search(r"(\d+) ementas", texto)
        or re.search(r"(\d+) sentenças", texto)
    )
    if achado is None:
        raise ValueError("nenhum formato de contagem reconhecido")
    return int(achado.group(1))
```

**(b) Aninhado com poucos ramos**, três pares de `for` e `if`, cada um dentro do anterior:

```python
def advogados_do_polo(processos, polo):
    """Lista os pares (processo, OAB) dos advogados de um polo."""
    oabs = []
    for processo in processos:
        if processo.get("partes"):
            for parte in processo["partes"]:
                if parte["polo"] == polo:
                    for advogado in parte.get("advogados", []):
                        if advogado.get("oab"):
                            oabs.append((processo["id_cnj"], advogado["oab"]))
    return oabs
```

| Exemplo | CCN (lizard) | Cognitivo (complexipy) | Leitura |
|---|---:|---:|---|
| (a) `extrair_total_resultados` | 16 | 2 | sequência plana, legível apesar do CCN; só o lizard pega |
| (b) `advogados_do_polo` | 7 | 21 | aninhada, só o cognitivo pega |

Números medidos com lizard 1.24.0 e complexipy 8.0.1. Em (a), o lizard soma +1 por `or` e +1 pelo `if`, enquanto o complexipy conta a sequência de `or` uma vez só. Em (b), cada estrutura paga +1 mais a profundidade em que está: o `if` mais interno custa 6 sozinho, embora a função tenha só seis pontos de decisão.

### Diagnóstico sob demanda (não roda em pre-commit nem CI)

```bash
uv run lizard src               # ciclomático (CCN) + NLOC + tokens + nº de params, por função
uv run complexipy -i -s desc src  # cognitivo por função, ordenado do maior para o menor
```

São as ferramentas a rodar antes de mexer num parser, para ver onde a dívida está concentrada — cada uma por uma lente.

### Gate planejado (ainda não ativo)

```bash
uv run complexipy --snapshot-create src   # baseline; o CI compara e falha só em regressão (grandfather)
uv run lizard -C 15 -w src                 # ciclomático: warning (e exit≠0) acima de CCN 15
```

Ligar um gate hoje deixaria o CI vermelho (várias funções acima do limiar). O gate entra no CI (job `quality`, #101) **depois** que as piores funções forem refatoradas — liderado pelo `complexipy --snapshot` (ratchet que congela o estado atual e só barra pioras), com o `lizard` como segunda lente. Refs #307, #101.

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
4. **Pydantic schema** de Input em `src/juscraper/courts/<xx>/schemas.py` ou no diretório compartilhado da família, com `extra="forbid"`. Escolher a base pelo tipo de endpoint em **Schemas pydantic** e declarar apenas filtros aceitos pelo método público.
5. **Teste de schema** em `tests/<xx>/test_<endpoint>_schema_contract.py` ou em `tests/schemas/`: validar parâmetros documentados, defaults e rejeição de valores fora do domínio. A instanciação direta do modelo rejeita kwargs desconhecidos com `ValidationError`; o contrato do método público deve conferir a conversão para `TypeError` quando todos os erros são `extra_forbidden`.
6. **Teste de propagação de filtros** em `tests/<xx>/test_<endpoint>_filters_contract.py`: chama o método público passando **todos** os filtros simultaneamente e o matcher (`urlencoded_params_matcher`/`json_params_matcher`/`query_param_matcher`) confirma que cada filtro chegou no body/params. Fecha o gap onde o happy-path com filtros vazios não detecta uma quebra de propagação.
7. **Cobertura mínima de aliases deprecados** no `test_<endpoint>_filters_contract.py`: um teste para **cada** alias que o scraper aceita em `normalize_pesquisa`/`normalize_datas`, assertando o `DeprecationWarning` + (quando aplicável) que o valor cai no body/params como o canônico. Exemplos: `query`/`termo` se o endpoint tem busca textual; `data_inicio`/`data_fim` se o endpoint tem filtro de data. Quando o alias vira noop silencioso (ex.: `data_inicio` num tribunal que só suporta `data_publicacao`), testar que o `DeprecationWarning` + o `UserWarning` de `warn_unsupported` são emitidos juntos.
8. **Sem `@pytest.mark.integration`** no contrato.
9. **Sem dependência de rede, relógio ou TLS real**. Adapter TLS custom: testar só montagem (`isinstance`).
10. **Fluxos multi-step com ordem obrigatória** usam `responses.registries.OrderedRegistry`.
11. **Captchas, tokens dinâmicos e libs externas** (`txtcaptcha`, `browser_cookie3`) são **mockados** — nunca invocados. Injetar fakes via `mocker.patch.dict(sys.modules, ...)` para lazy imports ausentes das deps.
12. **Entry no CHANGELOG** em `[Unreleased]/Added`.
13. **Payload builders públicos** em `courts/<xx>/download.py` sempre que o script de captura precisar reusar o dict/body enviado ao backend. Extrair como função de nome público (`build_<endpoint>_payload` — **sem underscore inicial**) + constante da URL base (`BASE_URL`, `RESULTS_PER_PAGE`, etc.). O script em `tests/fixtures/capture/<xx>.py` importa esses helpers em vez de redefinir o payload inline — qualquer mudança no scraper quebra a captura, evitando drift silencioso. Helpers privados (`_`) em módulos de download ficam reservados para lógica interna não reusada pelo capture script.
14. **Base recomendada: `juscraper.core.http.HTTPScraper`** (em vez de `BaseScraper` direto) para raspadores **novos**. Ela cria `self.session = requests.Session()`, expõe o hook `_configure_session(session)` (mesmo contrato do `EsajSearchScraper`), oferece `_request_with_retry(method, url, *, session=None, max_retries=3)` com backoff exponencial para 429/5xx + respeito a `Retry-After` numérico, e centraliza a validação de `session=` (resolve #185). Tribunais existentes ainda em `BaseScraper` migram pelas Fases 1-4 do refactor #194 — tribunais novos já podem (e devem) herdar de `HTTPScraper`.

## Schemas pydantic

### Onde ficam os modelos

- `src/juscraper/schemas/cjsg.py`: `SearchBase` para busca textual e `OutputCJSGBase` para o resultado. `SearchBase` herda paginação e não inclui filtros de data, pois nem todo tribunal os suporta.
- `src/juscraper/schemas/mixins.py`: contratos compartilhados de paginação, datas e relatoria. Compor apenas os mixins aplicáveis ao endpoint; filtros não suportados devem ser rejeitados por `extra="forbid"`.
- `src/juscraper/schemas/consulta.py` — `CnjInputBase` (`id_cnj: str | list[str]`), `OutputCnjConsultaBase` para cpopg/cposg/JusBR.
- `src/juscraper/courts/_<familia>/schemas.py`: schemas compartilhados pela família, sujeitos à **Regra de generalização** em `CLAUDE.md` > **Arquitetura**.
- `src/juscraper/courts/<xx>/schemas.py` / `aggregators/<yy>/schemas.py` — um arquivo por tribunal/agregador com Input/Output de todos os endpoints.

### Registro, paridade e wiring

`tests/schemas/test_schema_coverage.py` mantém `EXPECTED_COURT_SCHEMAS` e `EXPECTED_AGGREGATOR_SCHEMAS`, os registros de endpoints com modelos Input. Métodos stub com `NotImplementedError` ficam fora desse contrato. O schema pode existir como documentação executável antes de ser usado pelo método em runtime.

`tests/schemas/test_signature_parity.py` compara campos e parâmetros explícitos, descontando infraestrutura e aliases conhecidos. Em métodos com `**kwargs`, verifica se os parâmetros explícitos estão no schema, permitindo filtros adicionais no modelo. `_is_wired` reconhece atributos `INPUT_<ENDPOINT>`, inclusive herdados, e as exceções declaradas em `WIRED_WITHOUT_CLASS_ATTR`; esses casos são pulados na paridade. A presença no registro não comprova wiring: conferir o método e seus contratos de validação.

Para decidir quando conectar o schema ao método, seguir `CLAUDE.md` > **Testes**, que separa o PR de contratos da mudança de runtime.

### Nomes e tipos canônicos

As bases e os mixins em `src/juscraper/schemas/` definem os tipos compartilhados. `tests/schemas/test_canonical_types.py::DEPRECATED_SYNONYMS` mapeia os nomes substituídos; `TYPE_GRACE_PERIOD` e `SYNONYM_GRACE_PERIOD` registram exceções com justificativa. Consultar essas fontes ao criar campos, sem copiar suas listas para documentação.

O Output reflete o shape real do parser e usa `extra="allow"` para campos auxiliares do backend. Renomear chaves brutas para os nomes canônicos antes de construir o DataFrame; não preencher lacunas com valores provisórios. Campos específicos, como texto integral ou datas próprias do tribunal, continuam no schema concreto quando não representam o mesmo conceito de um campo compartilhado.

### Modelos são irmãos de `SearchBase`

Modelos de endpoints diferentes herdam da base apropriada e de mixins, não de outro modelo concreto. Por exemplo, `InputCJSGEsajPuro` e `InputCJSGTJSP` são irmãos porque suas APIs divergem. Para extrair campos compartilhados, aplicar a **Regra de generalização** em `CLAUDE.md` > **Arquitetura**.

### `paginas`: contrato único, redeclaração é drift

`PaginasMixin` em `src/juscraper/schemas/mixins.py` declara o campo e seus validadores; `SearchBase` o herda. Schemas concretos herdam esse contrato sem redeclarar `paginas`, evitando divergências de tipo, default e validação. `tests/schemas/test_paginas_acceptance.py` verifica as formas aceitas; limitações de runtime devem ser tratadas no contrato do endpoint.

### Tratamento de divergências de nome

- **Output**: divergências são corrigidas no parser via renomeação. Isso é **breaking change** declarado em `CHANGELOG.md`. Output bate o nome canônico após a renomeação.
- **Input**: divergências viram **alias deprecado** via `pop_deprecated_alias` (`src/juscraper/utils/params.py`), emitindo `DeprecationWarning`. O campo canônico não é removido do Input ao deprecar um alias.

### Pipeline canônico (wiring)

Usar `juscraper.utils.params.apply_input_pipeline_search` como referência para buscas: resolver aliases e validações específicas antes de instanciar o pydantic; construir o payload a partir do modelo validado. Essa ordem preserva os avisos de deprecação e as exceções específicas, em vez de transformá-los em erros genéricos do schema. `raise_on_extra_kwargs` converte a exceção em `TypeError` apenas quando todos os erros são `extra_forbidden`; nos demais casos, o chamador relança o `ValidationError` original. Os contratos de filtros de eSAJ exercitam essa ordem. Para limites de janela e coerção de datas, consultar a implementação do pipeline e a configuração do scraper.

### `session=` fica fora do schema pydantic (decisão #185)

Métodos públicos que aceitam `session: requests.Session | None = None` (caminho de transporte para reuso de cookies/TLS) **não declaram esse parâmetro no schema pydantic**. O parâmetro é detalhe de transporte, não filtro de backend, e a validação `isinstance(session, requests.Session)` fica centralizada em `juscraper.core.http.HTTPScraper._request_with_retry` — que levanta `TypeError` na fronteira quando recebe valor inválido. Tribunais ainda não migrados para `HTTPScraper` chamam essa mesma validação assim que migrarem (Fases 1-4 do refactor #194). Resolve #185.

### `BACKEND_DATE_FORMAT` é só formato de saída

Cada `Input*` declara um `BACKEND_DATE_FORMAT: ClassVar[str]` (default `"%d/%m/%Y"` para eSAJ; tribunais com backend ISO declaram `"%Y-%m-%d"`). Esse formato governa **apenas** o que sai para o backend — o que o pydantic guarda no campo e o que `validate_intervalo_datas` usa para parsear. Na **entrada** (kwargs vindos do usuário), o pipeline aceita as quatro variações de string (`DD/MM/AAAA`, `DD-MM-AAAA`, `AAAA-MM-DD`, `AAAA/MM/DD`) e também `datetime.date` / `datetime.datetime`, e coage para `BACKEND_DATE_FORMAT` antes da validação (refs #173). O autor de schema só precisa escolher o formato de saída e declarar; a tolerância de entrada é gratuita.

### Checklist ao adicionar um tribunal novo

1. Criar `courts/<xx>/schemas.py` com Input+Output para cada método **implementado**.
2. Herdar `SearchBase` + mixins aplicáveis; Output herda `OutputCJSGBase` + `OutputRelatoriaMixin`/`OutputDataPublicacaoMixin` conforme o parser entregue. Campos não-herdados do Output são declarados Optional.
3. Se o parser usa nomes divergentes do canônico (`classe_cnj`, `magistrado`, `nr_processo`, ...), renomear no parser antes de commitar — Output fica com o nome canônico.
4. Registrar em `tests/schemas/test_schema_coverage.py::EXPECTED_COURT_SCHEMAS` **e** `tests/schemas/test_output_parity.py::EXPECTED_COURT_OUTPUT_SCHEMAS`, rodar `pytest tests/schemas/`.
5. Se já refatorado, wirar o schema no método público seguindo o pipeline canônico de `_esaj/base.py`.

## Docstrings de métodos públicos com kwargs

Métodos públicos que recebem filtros em `**kwargs` precisam documentá-los, pois `inspect.signature` não mostra os campos aceitos pelo schema. Escrever docstrings em português, no estilo Google (`Args:`, `Returns:`, `Raises:`), seguindo o método `EsajSearchScraper.cjsg` em `src/juscraper/courts/_esaj/base.py`. Para override com schema próprio, usar `TJSPScraper.cjsg` como referência.

### Filtros e aliases

- Listar em `**kwargs` os filtros do schema correspondente, com os mesmos nomes e tipos; citar o schema em `See also:`. Mudanças de campos e docstring devem entrar juntas.
- Acrescentar a semântica que o modelo não expressa: interpretação do filtro, formato exigido pelo backend e exemplo de uso. Indicar nomes de campos do backend quando isso explicar por que um filtro exige IDs internos.
- Documentar defaults não óbvios e o significado de `None` para cada filtro; não presumir que todo campo seja opcional.
- Listar aliases deprecados em seção própria, conforme os que o endpoint realmente consome em `normalize_pesquisa`, `normalize_datas` e `pop_deprecated_alias`. As constantes em `src/juscraper/utils/params.py` são a fonte dos aliases compartilhados; conferir também a normalização específica do scraper. Informar o `DeprecationWarning` sem remover o campo canônico da documentação.

Estrutura para o método principal, adaptando parâmetros explícitos, filtros e exceções ao endpoint:

```text
"""Pesquisa jurisprudência de segundo grau do tribunal.

<Efeitos específicos, como delegação e limpeza de downloads.>

Args:
    pesquisa (str): <Semântica e restrições da busca.>
    paginas (int | list | range | None): Páginas 1-based;
        None busca todas.
    **kwargs: Filtros aceitos por :class:`<InputDoEndpoint>`:

        * ``<campo_do_schema>`` (<tipo>): <Semântica do filtro.>

Aliases deprecados:
    * ``<alias_aceito>`` -> ``<campo_canonico>`` (DeprecationWarning).

Raises:
    TypeError: Quando todos os erros são kwargs desconhecidos.
    ValidationError: Para os demais erros de validação do schema.
    <ExcecaoEspecifica>: <Condição validada antes do pydantic.>

Returns:
    pd.DataFrame: <Colunas principais e significado do resultado.>

Exemplo:
    <Chamada pública válida, usando nomes canônicos.>

See also:
    :class:`<InputDoEndpoint>`: fonte dos filtros aceitos.
"""
```

### Métodos de download

Exemplos e a lista de filtros ficam no método principal, como `cjsg` ou `cjpg`. O par `*_download` descreve somente suas diferenças, como `diretorio` e o retorno do caminho, e referencia a lista de filtros com `:meth:` apontando para o método principal. Isso evita manter uma segunda lista que pode divergir do schema.

### Cobertura de paridade

`tests/schemas/test_docstring_parity.py::test_docstring_lists_schema_fields` exige igualdade entre os filtros documentados e os campos do modelo nos endpoints registrados em `CASES`. Ao adicionar um método ou override com schema próprio e filtros em `**kwargs`, registrar o caso. O teste não descobre automaticamente novos endpoints.

`test_download_docstring_references_toplevel` verifica a referência `:meth:` nos pares registrados em `DOWNLOAD_REFERENCE_CASES`. Registrar novos pares nessa lista. Se houver necessidade de listar filtros também em um download, justificar a exceção no PR e incluir o método em `CASES`, para que a lista tenha cobertura de paridade.

Executar `uv run pytest tests/schemas/test_docstring_parity.py` após alterar esses contratos.

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
- `_validate_pesquisa(pesquisa, *, endpoint)`: rejeitar o termo de busca já resolvido antes de o auto-chunk dividir a busca em janelas (TJSP aplica o limite de 120 chars). Os caminhos de janela única e `count_only` não passam por ele: o tribunal valida também no próprio `<endpoint>_download` e no probe de contagem

**Não adicionar `if tribunal == "X"` no código compartilhado.** Se a particularidade não encaixar via hook/atributo, prefira um scraper próprio fora da família em vez de vazar a diferença na base.

### 5. Quando generalizar algo para `_esaj/` (regra de promoção sob demanda)

Aplicar a **Regra de generalização** em `CLAUDE.md` > **Arquitetura**. Validators, exceções e helpers específicos permanecem no diretório do tribunal enquanto não houver evidência para compartilhá-los. Os hooks de `EsajSearchScraper` permitem essas diferenças sem condicionar o código comum ao nome do tribunal.
