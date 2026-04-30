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
- Preferir trabalhar em worktree com branch específica para a mudança que desejar implementar.

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

1. **Script de captura** em `tests/fixtures/capture/<xx>.py` que **sempre** exercita o scraper contra o backend real do tribunal e salva as respostas cruas em `tests/<xx>/samples/<endpoint>/<cenario>.<ext>`. Nunca sintetizar samples a mao — o shape do backend e a fonte da verdade do contrato, nao adivinhacao. Se o backend estiver indisponivel no momento, documentar e abrir issue separada em vez de mockar campos. Minimo de 3 cenarios por endpoint: typical, sem resultados, pagina unica. Saneamento pos-captura (truncar Base64, remover highlights de Elasticsearch, etc.) e OK e fica dentro do proprio script — ver `tests/fixtures/capture/tjrs.py` como referencia.
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
6a. **Cobertura minima de aliases deprecados** no `test_<endpoint>_filters_contract.py`: um teste para **cada** alias que o scraper aceita em `normalize_pesquisa`/`normalize_datas`, assertando o `DeprecationWarning` + (quando aplicavel) que o valor cai no body/params como o canonico. Exemplos: `query`/`termo` se o endpoint tem busca textual; `data_inicio`/`data_fim` se o endpoint tem filtro de data. Quando o alias vira noop silencioso (ex.: `data_inicio` num tribunal que so suporta `data_publicacao`), testar que o `DeprecationWarning` + o `UserWarning` de `warn_unsupported` sao emitidos juntos.
7. **Sem `@pytest.mark.integration`** no contrato.
8. **Sem dependencia de rede, relogio ou TLS real**. Adapter TLS custom: testar so montagem (`isinstance`).
9. **Fluxos multi-step com ordem obrigatoria** usam `responses.registries.OrderedRegistry`.
10. **Captchas, tokens dinamicos e libs externas** (`txtcaptcha`, `browser_cookie3`) sao **mockados** — nunca invocados. Injetar fakes via `mocker.patch.dict(sys.modules, ...)` para lazy imports ausentes das deps.
11. **Entry no CHANGELOG** em `[Unreleased]/Added`.
12. **Payload builders publicos** em `courts/<xx>/download.py` sempre que o script de captura precisar reusar o dict/body enviado ao backend. Extrair como funcao de nome publico (`build_<endpoint>_payload` — **sem underscore inicial**) + constante da URL base (`BASE_URL`, `RESULTS_PER_PAGE`, etc.). O script em `tests/fixtures/capture/<xx>.py` importa esses helpers em vez de redefinir o payload inline — qualquer mudanca no scraper quebra a captura, evitando drift silencioso. Helpers privados (`_`) em modulos de download ficam reservados para logica interna nao reusada pelo capture script.

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

Todo endpoint publico de scraper (`cjsg`, `cjpg`, `cpopg`, `cposg`, `listar_processos`, `auth`, `download_documents`, ...) tem schema `Input<Endpoint><Tribunal>` em `courts/<xx>/schemas.py` ou `aggregators/<yy>/schemas.py`, **inclusive para tribunais ainda nao refatorados** — o schema vive como documentacao executavel da API publica ate o wiring (chamada explicita no metodo publico). Ganhos: rejeita kwargs desconhecidos via `extra="forbid"` (quando wired), nome do campo pydantic fixa singular/plural (#68), substitui validators espalhados.

Wiring tem duas fases: **schema-arquivo** (todos — existe e bate com a assinatura, protegido contra drift por `tests/schemas/test_signature_parity.py`) e **wired** (hoje: TJAC/TJAL/TJAM/TJCE/TJMS + TJSP `cjsg`/`cjpg` — metodo publico invoca o schema; kwargs desconhecidos viram `TypeError` amigavel via `_raise_on_extra` em `juscraper.courts._esaj.base`).

**Wiring segue o refactor #84, nao o PR de contratos.** Contratos de teste offline (padrao #119 / #120) sao *rede de seguranca anterior* a refatoracao e nao devem incluir wiring de schema no mesmo PR. Wiring entra junto com a refatoracao estrutural da familia (ou em PR dedicado imediatamente apos a refatoracao), nunca antes. Misturar os dois escopos viola a regra 1 do #84 (uma mudanca estrutural por vez) e torna o PR de contrato dificil de revisar. Se uma issue de contratos "deixa em aberto" se faz wiring, o default e NAO wirar — abrir follow-up se necessario.

Pipeline canonico implementado em `src/juscraper/courts/_esaj/base.py` e exercitado em `tests/tj{ac,al,am,ce,ms,sp}/test_cjsg_filters_contract.py`. Ao wirar tribunal novo, copiar a ordem de la: aliases (via `normalize_pesquisa`/`normalize_datas`) → validators custom → pydantic → build body a partir do modelo. Motivos: aliases antes do pydantic (senao viram `TypeError` generico); validators custom antes (senao viram wrapped em `ValidationError`); `_raise_on_extra` depois (so `extra_forbidden` deve virar `TypeError` — erro de tipo real sobe natural).

### Onde ficam os modelos

- `src/juscraper/schemas/cjsg.py` — `SearchBase` (pesquisa, paginas: **1-based, contrato unico**) e `OutputCJSGBase` (processo, ementa?, data_julgamento?). Sem filtros de data na base.
- `src/juscraper/schemas/mixins.py` — Input: `DataJulgamentoMixin`, `DataPublicacaoMixin`. Output: `OutputRelatoriaMixin` (relator, orgao_julgador), `OutputDataPublicacaoMixin` (data_publicacao). Tribunal herda se aplicavel; quem nao suporta deixa `extra="forbid"` rejeitar.
- `src/juscraper/schemas/consulta.py` — `CnjInputBase` (`id_cnj: str | list[str]`), `OutputCnjConsultaBase` para cpopg/cposg/JusBR.
- `src/juscraper/courts/_<familia>/schemas.py` — compartilhado pela familia (ex.: `InputCJSGEsajPuro`, `OutputCJSGEsaj`). Criar so com 2+ ocorrencias (Regra 1 do #84).
- `src/juscraper/courts/<xx>/schemas.py` / `aggregators/<yy>/schemas.py` — um arquivo por tribunal/agregador com Input/Output de todos os endpoints.

### OOP dirigida por evidencia

Campo em >= 2 Inputs/Outputs concretos sobe para base/mixin; abaixo disso fica inline no tribunal. Compartilhados atuais: **Input** — `pesquisa`/`paginas` (25 tribunais), `data_julgamento_*` (13), `data_publicacao_*` (11), `id_cnj` (3); **Output** — `processo`/`ementa`/`data_julgamento` (base), `relator`/`orgao_julgador` (>=10 parsers), `data_publicacao` (>=9 parsers). A disciplina (Regra 1 do #84) evita refactor em cascata quando o desenho inicial nao encaixa.

### Nomes canonicos de coluna

Conceitos equivalentes tem o mesmo nome em todos os tribunais. Divergencias de Output sao corrigidas no parser com renomeacao (breaking change declarado em CHANGELOG) + Output batendo o nome canonico; divergencias de Input viram deprecacao do alias antigo via `pop_deprecated_alias` (`src/juscraper/utils/params.py`). Canonicos atuais:

- `processo` (nao `nr_processo`, `numero_unico`, `numero_cnj`)
- `classe` (nao `classe_cnj`, `classe_judicial`)
- `assunto` (nao `assunto_cnj`, `assunto_principal`)
- `relator` (nao `magistrado`)
- `numero_processo` (no Input; o campo de saida e `processo`)

Excecoes documentadas caso a caso: `texto` (TJGO — documento inteiro, nao ementa); `dt_juntada` (TJES — data da juntada, distinta de `data_julgamento`); `tipo_*` (nao unificado — `tipo_ato`/`tipo_julgamento`/`tipo_decisao` sao conceitos sobrepostos mas distintos).

### `paginas` e contrato unico

`SearchBase.paginas: int | list[int] | range | None = None` e **1-based em todos os raspadores**. Schemas concretos **nao redeclaram** (redeclaracao cosmetica e drift; `SearchBase` e fonte unica). Normalizacao runtime acontece em `normalize_paginas` antes do pydantic. Tribunais que nao aceitam alguma forma (ex.: DataJud so aceita `range`) viram xfail em `tests/schemas/test_paginas_acceptance.py` e correcao em PR proprio.

### Regras (qualquer violacao quebra `tests/schemas/`)

- Modelos de endpoints diferentes sao **irmaos** de `SearchBase`, nao herdam entre si (ex.: `InputCJSGEsajPuro` e `InputCJSGTJSP` divergem por historico da API).
- Campos do Input batem **byte-a-byte** com a assinatura do metodo publico. `test_signature_parity.py` exclui so infra (`session`, `diretorio`, `download_path`, `base_url`) via allowlist.
- **Nao redeclarar `paginas`** em schema concreto — `SearchBase.paginas` e a fonte unica (contrato 1-based, 4 formas aceitas).
- Output reflete shape real do parser — sem `"Provisorio"`. `test_output_parity.py` valida que campos nao-herdados do Output aparecem como string literal no source do parser; parsers dinamicos (label-based) e passthrough sao skip com razao explicita.
- `Output*` usa `extra="allow"` para campos auxiliares (`cod_*`, `id_*`, hashes) que o parser entrega mas nao cabem no contrato explicito.
- Colunas de saida semanticamente equivalentes tem o **mesmo nome** em todos os tribunais (ver "Nomes canonicos de coluna" acima). Parsers renomeiam chaves brutas do backend (`classe_cnj` -> `classe`) antes de construir o DataFrame.
- Validators que levantam excecoes custom (ex.: `QueryTooLongError`) rodam no scraper **antes** do pydantic. Padrao: `validate_pesquisa_length(pesquisa, endpoint="CJSG")` no topo do metodo.
- Aliases deprecados (`query`/`termo`, `data_inicio`/`data_fim`, `data_*_de`/`_ate`, `nr_processo`, `numero_cnj`, `magistrado`, `classe_judicial`, `classe_cnj`, `assunto_cnj`) sao popados em `normalize_pesquisa`/`normalize_datas`/`pop_deprecated_alias` (`src/juscraper/utils/params.py`) antes do pydantic, emitindo `DeprecationWarning`. Nao remover o campo canonico do Input ao deprecar um alias.
- Nao criar schema para metodo stub `NotImplementedError` — sem API estavel para documentar. Criar junto quando o metodo for implementado.
- Nao criar mixin/base com 1 ocorrencia concreta — esperar o 2o caso.

### Checklist ao adicionar um tribunal novo

1. Criar `courts/<xx>/schemas.py` com Input+Output para cada metodo **implementado**.
2. Herdar `SearchBase` + mixins aplicaveis; Output herda `OutputCJSGBase` + `OutputRelatoriaMixin`/`OutputDataPublicacaoMixin` conforme o parser entregue. Campos nao-herdados do Output sao declarados Optional.
3. Se o parser usa nomes divergentes do canonico (`classe_cnj`, `magistrado`, `nr_processo`, ...), renomear no parser antes de commitar — Output fica com o nome canonico.
4. Registrar em `tests/schemas/test_schema_coverage.py::EXPECTED_COURT_SCHEMAS` **e** `tests/schemas/test_output_parity.py::EXPECTED_COURT_OUTPUT_SCHEMAS`, rodar `pytest tests/schemas/`.
5. Se ja refatorado, wirar o schema no metodo publico seguindo o pipeline canonico de `_esaj/base.py`.

## Docstrings de metodos publicos com `**kwargs`

Metodos publicos de scraper que aceitam filtros via `**kwargs` validados por schema pydantic (`cjsg`, `cjsg_download`, `cjpg`, `cjpg_download` da familia eSAJ refatorada e analogos futuros) seguem um padrao comum de docstring. O motivo: o pydantic e a fonte unica da verdade dos filtros, mas `inspect.signature` mostra so `pesquisa`/`paginas`/`**kwargs` — o usuario fica sem visibilidade dos filtros aceitos. A docstring fecha esse buraco.

Idioma: **portugues** (vale para `src/`; `docs/*.qmd` continua em ingles por causa do build do Quarto). Estilo: Google docstring (`Args:`/`Returns:`/`Raises:`).

Estrutura (template):

```
"""<Resumo em 1 frase, presente do indicativo, terminando em ponto>.

<Paragrafo opcional descrevendo o efeito (delegacao, cleanup, metodo
HTTP, particularidade) — max. 3 linhas.>

Args:
    pesquisa (str): <descricao>. <constraint — ex.: "max 120 chars">.
    paginas (int | list | range | None): Paginas 1-based; ``None`` baixa
        todas. Default ``None``.
    diretorio (str | None): Sobrescreve ``download_path`` para esta
        chamada. Default ``None``.
    **kwargs: Filtros aceitos pelo schema :class:`<InputXxxYyy>`.
        Listados abaixo (todos opcionais; ``None`` = sem filtro):

        * ``ementa`` (str): <descricao backend>.
        * ``classe`` (str | list[str]): <descricao>. Backend:
          ``classeTreeSelection.values``.
        * ``varas`` (list[str]): IDs internos de vara (TJSP usa formato
          ``"X-Y-Z"``). Backend: ``varasTreeSelection.values``.
        * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
          ``DD/MM/AAAA``.
        * <demais filtros do schema>

Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
    * ``query`` / ``termo`` -> ``pesquisa``
    * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
    * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
    * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

Raises:
    TypeError: Quando um kwarg desconhecido e passado (via
        ``_raise_on_extra``).
    ValidationError: Quando um filtro tem formato invalido.
    QueryTooLongError: Quando ``pesquisa`` excede o limite do tribunal
        (apenas TJSP, 120 chars).

Returns:
    pd.DataFrame: <descricao do shape — colunas principais>.
    str: Caminho do diretorio de download (apenas em ``*_download``).

Exemplo:
    >>> import juscraper as jus
    >>> tjsp = jus.scraper("tjsp")
    >>> df = tjsp.cjpg("dano moral", paginas=range(1, 3),
    ...                varas=["1-1-1"], classes=["12728"])

See also:
    :class:`<InputXxxYyy>` — schema pydantic e a fonte da verdade dos
    filtros aceitos.
"""
```

Regras:

1. **Cada filtro listado na docstring deve existir como campo do schema pydantic correspondente.** Se um campo sai do schema, a docstring muda junto. Se entra, idem. A docstring cita explicitamente o schema (`See also:`) para o usuario seguir a fonte da verdade.
2. **Aliases deprecados** ficam em secao propria — listar todos os que `normalize_pesquisa`/`normalize_datas`/`pop_deprecated_alias` consomem para esse endpoint. Aliases nao listados na docstring ainda funcionam (o codigo de normalizacao e quem decide), mas a expectativa do projeto e manter a docstring sincronizada.
3. **Default so listar quando nao-None ou nao-obvio** (ex.: `paginas=None`, `tipo_decisao="acordao"`, `baixar_sg=True`).
4. **Backend hint** (ex.: `varasTreeSelection.values`) e opcional. Use quando ajuda o usuario a entender por que o filtro e uma lista de IDs e nao um nome amigavel — o usuario precisa saber que tem que descobrir o ID externamente.
5. **Exemplo so em metodos top-level** (`cjsg`, `cjpg`). Os pares `*_download` ficam mais curtos: descrevem so o que diferencia (retorna path, aceita `diretorio`) e referenciam o metodo top-level via `:meth:` para a lista de filtros. **A referencia via `:meth:` e parte do contrato, nao apenas estilo** — fiscalizada por `tests/schemas/test_docstring_parity.py::test_download_docstring_references_toplevel`. Substituir a referencia por bullets duplicados (regredindo o padrao) faz `*_download` driftar do schema sem alarme; se algum caso futuro precisar mesmo listar bullets, registrar o endpoint em `CASES` e justificar no PR.
6. **A docstring nao duplica o que o schema ja diz.** Tipos e nomes canonicos vem do schema; a docstring agrega so o que o pydantic nao consegue: semantica do parametro, formato esperado pelo backend, exemplo de uso. Quando der drift, a fonte certa e o schema.
7. **Cobertura no teste de paridade.** A regra 1 e fiscalizada por `tests/schemas/test_docstring_parity.py::test_docstring_lists_schema_fields`, que so cobre os endpoints listados em `CASES`. Ao adicionar um override de docstring com schema proprio (cenario `INPUT_CJSG = InputCJSGTJXX` da secao "Raspadores eSAJ: como adicionar um novo tribunal > API divergente"), registrar o caso em `CASES` para nao perder cobertura. O override `TJSPScraper.cjsg` e o exemplo canonico.

Referencia: o metodo `EsajSearchScraper.cjsg` em `src/juscraper/courts/_esaj/base.py` e a docstring "ouro" para a familia eSAJ.

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
- **Comentarios em PRs, issues e revisoes de codigo neste repo devem ser sempre em portugues.** Vale tambem para mensagens de commit (corpo pode ser bilingue quando convir, mas o assunto e a explicacao do "porque" ficam em portugues). Excecao unica: arquivos em `docs/` continuam em ingles por causa do build do Quarto (ver secao "Documentacao" abaixo).

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
