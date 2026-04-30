# CLAUDE.md

## Visao geral do projeto

juscraper e uma biblioteca Python para raspagem de dados de tribunais brasileiros. Coleta dados de jurisprudencia (acordaos, decisoes) do TJDFT, TJPR, TJRS, TJSP e outros tribunais.

## Arquitetura

- Codigo-fonte em `src/juscraper/`
- Tribunais organizados hierarquicamente: `juscraper.courts.<tribunal>.client` (ex: `juscraper.courts.tjrs.client.TJRSScraper`)
- A factory function publica e `juscraper.scraper()`
- Nomes de classes seguem PEP 8 CamelCase: `TJDFTScraper`, `TJPRScraper`, `TJRSScraper`, `TJSPScraper`
- **Regra 1 do refactor #84:** generalizar (mover para `_<familia>/`, criar mixin/base) so com **2+ ocorrencias concretas**. Duplicar com 1 caso e mais barato que abstrair errado.

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

### Comandos

- `pytest` — roda contrato + granular (offline, ~0.5s). **Default exclui integracao.**
- `pytest -m integration` — roda so integracao (lento, hit live).
- `pytest -m ""` — roda tudo (offline + integracao).
- `pytest tests/tjsp` — escopo a um tribunal.
- `--strict-markers` esta ativo — todo marker deve ser registrado no `pyproject.toml`.

### Regras para autor de teste

- Toda mudanca em parser HTML/JSON deve incluir/atualizar sample em `tests/<tribunal>/samples/<endpoint>/`.
- Testes de contrato afirmam **schema do DataFrame** (colunas obrigatorias) e, quando relevante, **payload enviado** (matchers do `responses`).
- Testes que tocam rede ficam marcados com `@pytest.mark.integration`.
- Cassetes (`pytest-recording`) sao adotados caso a caso; medir peso agregado antes de generalizar (limite indicativo: ~20 MB no repo).
- Antes de refatorar um tribunal pela #84, ele precisa ter contratos passando.

Piramide de testes (sufixos `*_contract.py` / `*_granular.py` / `*_cassette.py` / `*_integration.py`), ferramentas (`responses`, `pytest-mock`, `pytest-recording`) e checklist de 12 itens para adicionar raspador novo: ver `CONTRIBUTING.md` > **Tests** e **Adding a new tribunal**.

## Convencao de API para raspadores

- Busca: `pesquisa` como nome padrao em todos os scrapers
- Datas: `data_julgamento_inicio/fim`, `data_publicacao_inicio/fim`
- Alias generico: `data_inicio/fim` mapeia para `data_julgamento_inicio/fim`
- Nomes antigos (`query`, `termo`, `_de/_ate`) aceitos com `DeprecationWarning`
- Paginacao: `paginas: int | list | range | None`, default `None` (todas as paginas). Sempre 1-based: `range(1, 4)` baixa paginas 1, 2 e 3; `paginas=3` e equivalente a `range(1, 4)`.
- Normalizacao centralizada em `src/juscraper/utils/params.py`
- **Validacao da API publica via pydantic com `extra="forbid"`**. Kwargs desconhecidos levantam `ValidationError` em vez de serem silenciosamente ignorados.

Referencia completa de parametros e migracao: `docs/api-conventions.qmd`.

## Schemas pydantic (refs #93)

Todo endpoint publico (`cjsg`, `cjpg`, `cpopg`, `cposg`, `listar_processos`, `auth`, `download_documents`, ...) tem schema `Input<Endpoint><Tribunal>` em `courts/<xx>/schemas.py` ou `aggregators/<yy>/schemas.py`, **inclusive para tribunais ainda nao refatorados** — o schema vive como documentacao executavel ate o wiring. Wired hoje: TJAC/TJAL/TJAM/TJCE/TJMS + TJSP `cjsg`/`cjpg`.

**Wiring segue o refactor #84, nao o PR de contratos.** Contratos offline (padrao #119/#120) sao rede de seguranca *anterior* a refatoracao; wiring entra junto com a refatoracao estrutural (ou em PR dedicado imediatamente apos), nunca no mesmo PR de contrato. Default: NAO wirar quando uma issue de contratos deixa em aberto — abrir follow-up.

### Regras always-on (qualquer violacao quebra `tests/schemas/`)

- **Nomes canonicos de coluna** (Input e Output): `processo` (nao `nr_processo`/`numero_unico`/`numero_cnj`), `classe` (nao `classe_cnj`/`classe_judicial`), `assunto` (nao `assunto_cnj`/`assunto_principal`), `relator` (nao `magistrado`), `numero_processo` no Input (campo de saida e `processo`). Excecoes: `texto` (TJGO), `dt_juntada` (TJES), `tipo_*` (sem unificacao).
- **Nao redeclarar `paginas`** em schema concreto — `SearchBase.paginas: int | list[int] | range | None = None` e fonte unica (1-based, 4 formas aceitas).
- Campos do Input batem **byte-a-byte** com a assinatura do metodo publico (`tests/schemas/test_signature_parity.py` exclui so infra via allowlist).
- `Input*` usa `extra="forbid"`; `Output*` usa `extra="allow"` para auxiliares (`cod_*`, `id_*`, hashes).
- Validators custom (ex.: `QueryTooLongError`) rodam **antes** do pydantic. Padrao: `validate_pesquisa_length(pesquisa, endpoint="CJSG")` no topo do metodo.
- Aliases deprecados sao popados em `normalize_pesquisa`/`normalize_datas`/`pop_deprecated_alias` antes do pydantic, emitindo `DeprecationWarning`. Nao remover o campo canonico ao deprecar um alias.
- Output reflete shape real do parser — sem `"Provisorio"`. Parsers renomeiam chaves brutas (`classe_cnj` -> `classe`) antes de construir o DataFrame.
- Nao criar schema para metodo stub `NotImplementedError`. Nao criar mixin/base com 1 ocorrencia (Regra 1 do #84).

Onde ficam os modelos, pipeline canonico de wiring e checklist ao adicionar tribunal: `CONTRIBUTING.md` > **Schemas pydantic**.

## Raspadores eSAJ

A familia eSAJ (TJAC/TJAL/TJAM/TJCE/TJMS/TJSP) compartilha a infra em `src/juscraper/courts/_esaj/`. Caso tipico: subclasse de `EsajSearchScraper` com `BASE_URL` + `TRIBUNAL_NAME`. Hooks para casos de borda: `_configure_session(session)` (TLS/cookies), `INPUT_CJSG` (pydantic proprio), `CJSG_CHROME_UA` / `CJSG_EXTRACT_CONVERSATION_ID` (atributos de classe), `_build_cjsg_body(inp)` (shape divergente do form).

**Nao adicionar `if tribunal == "X"` no codigo compartilhado.** Se a particularidade nao encaixar via hook/atributo, prefira um scraper proprio fora da familia. Promover algo de `courts/<xx>/` para `_esaj/` so com 2+ ocorrencias (Regra 1 do #84).

Tutorial completo com exemplos de codigo (caso tipico, customizacao TLS, API divergente): `CONTRIBUTING.md` > **Adding an eSAJ tribunal**.

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
        ``raise_on_extra_kwargs``).
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
7. **Cobertura no teste de paridade.** A regra 1 e fiscalizada por `tests/schemas/test_docstring_parity.py::test_docstring_lists_schema_fields`, que so cobre os endpoints listados em `CASES`. Ao adicionar um override de docstring com schema proprio (cenario `INPUT_CJSG = InputCJSGTJXX` em `CONTRIBUTING.md` > **Adding an eSAJ tribunal** > "API divergente"), registrar o caso em `CASES` para nao perder cobertura. O override `TJSPScraper.cjsg` e o exemplo canonico.

Referencia: o metodo `EsajSearchScraper.cjsg` em `src/juscraper/courts/_esaj/base.py` e a docstring "ouro" para a familia eSAJ.

## Extracao de numero de paginas/resultados em raspadores HTML

Paginas de tribunais mudam estrutura sem aviso. Use **selecao em cascata** (varios seletores tentados em sequencia) e **regex em cascata** (numero no final, depois `(?<=de )[0-9]+`, depois descritores opcionais, ultimo recurso: maior `\d+`). Referencia canonica: `cjsg_n_pags` em `src/juscraper/courts/tjsp/cjsg_parse.py`. Cada formato suportado precisa de sample em `tests/<tribunal>/samples/` + teste unitario.

## Regras de workflow no GitHub

- Nunca tentar aprovar o proprio PR (`gh pr review --approve` falha para o autor do PR)
- Usar `gh pr review --comment` para deixar notas de revisao nos proprios PRs
- Sempre fazer push para uma branch de feature e abrir PR — nunca fazer push direto na main
- **Merge de PRs: sempre usar commit de merge (`gh pr merge <n> --merge --delete-branch`)**, nunca squash nem rebase. O commit de merge preserva cada commit individual da branch *e* adiciona um commit `Merge pull request #<n> from <branch>` que marca o limite do PR — `git log --all --graph` continua mostrando o que entrou em cada PR. Squash perde a granularidade dos commits; rebase perde o limite do PR. Deletar a branch remota mantem a lista enxuta (a branch continua acessivel via `gh pr checkout <n>`).
- **Comentarios em PRs, issues e revisoes de codigo neste repo devem ser sempre em portugues.** Vale tambem para mensagens de commit (corpo pode ser bilingue quando convir, mas o assunto e a explicacao do "porque" ficam em portugues). Excecao unica: arquivos em `docs/` continuam em ingles (build do Quarto).

## Changelog

- Seguimos o padrao [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- Toda mudanca relevante deve ser registrada em `CHANGELOG.md` sob `[Unreleased]`. Categorias: Added, Changed, Deprecated, Removed, Fixed, Security
- **Secoes de versoes ja lancadas (`## [0.2.1]`, `## [0.2.0]`, ...) sao imutaveis.** Toda entrada nova vai em `[Unreleased]`, mesmo que corrija algo introduzido na ultima versao.
- **Antes de inserir uma entrada, confirme que ela cai *acima* do primeiro heading `## [x.y.z]` do arquivo.** Se `[Unreleased]` estiver sem subsecoes (`### Added/Changed/Fixed/...`), crie a subsecao necessaria.
- **Todo commit de `feat:`, `fix:`, `refactor:` ou `deprecated:` com efeito observavel pelo usuario deve incluir a entrada em `[Unreleased]` no mesmo commit.** Mudancas puramente internas (testes, tipagem, rename de simbolo privado, docs) nao precisam.

## Documentacao

- Documentacao do projeto (em `docs/`) deve ser escrita em ingles
- Portugues causa problemas de encoding no build do site (Quarto + GitHub Actions)
