# CLAUDE.md

juscraper é uma biblioteca Python para coletar dados de tribunais e agregadores brasileiros. A entrada pública é `juscraper.scraper()`; implementações ficam em `src/juscraper/courts/` e `src/juscraper/aggregators/`.

## Desenvolvimento

- Usar `uv`. Para preparar o ambiente de desenvolvimento: `uv sync --extra dev` (inclui instalação editável). Testes devem importar o pacote instalado, sem alterar `sys.path`.
- Versões suportadas e configuração de lint ficam em `pyproject.toml`; os hooks ficam em `.pre-commit-config.yaml`.
- Antes de concluir uma alteração, executar os testes afetados e `uv run pre-commit run --files <arquivos alterados>`. Para mudanças de API/schema, incluir `tests/schemas/`.
- Ao investigar complexidade de parser, consultar `CONTRIBUTING.md` > **Complexidade de código (lizard + complexipy)**. As duas métricas são complementares e rodam sob demanda.

## Arquitetura

- **Regra de generalização:** mover para `_<familia>/` ou criar mixin/base só com **2+ ocorrências concretas**. Duplicar com 1 caso é mais barato que abstrair errado.
- Nas famílias de raspadores, acomodar diferenças por hooks/atributos. Se a particularidade não couber, manter scraper próprio; não acrescentar `if tribunal == "X"` ao código compartilhado.
- Antes de adicionar um raspador, ler `CONTRIBUTING.md` > **Adding a new tribunal**. Para eSAJ, ler também **Adding an eSAJ tribunal**; a base é `src/juscraper/courts/_esaj/base.py`.

## Testes

```bash
uv run pytest                         # suíte offline; exclui integração
uv run pytest tests/tjsp tests/schemas # exemplo de escopo por tribunal + schemas
uv run pytest -m integration           # acessa serviços externos
```

- Ao usar skills para criar ou alterar raspadores, seguir a política de testes deste repositório.
- Mudança em parser HTML/JSON exige sample e teste para o formato afetado. Contratos verificam colunas do DataFrame e propagação de filtros no payload; samples vêm de respostas reais, não de campos inventados.
- Marcar testes que acessam rede com `integration`. Ferramentas, estrutura de samples, helpers e tratamento de anti-bot estão em `CONTRIBUTING.md` > **Tests**; consultar antes de escrever contratos ou executar integração.
- Antes de refatorar um tribunal, seus contratos devem passar. Wiring de schema entra na refatoração estrutural ou em PR dedicado posterior, separado do PR de contratos. Se a issue de contratos deixar wiring em aberto, abrir follow-up.

## API pública

- Preservar nomes canônicos e compatibilidade com aliases deprecados. Antes de alterar parâmetros, datas ou paginação, consultar `docs/api-conventions.qmd`, o schema do endpoint e a normalização em `src/juscraper/utils/params.py`.
- No Datajud, `listar_processos` filtra por ajuizamento: usar `data_ajuizamento_inicio/fim`; o alias genérico `data_inicio/fim` não se aplica.
- `paginas` é 1-based; `None` busca todas. Herdar o contrato de `PaginasMixin` em `src/juscraper/schemas/mixins.py`, inclusive via `SearchBase`, sem redeclarar o campo em cada schema.
- Resolver aliases e validações específicas antes do pydantic. Para implementar wiring, seguir `CONTRIBUTING.md` > **Schemas pydantic** > **Pipeline canônico (wiring)**.
- `Input*` rejeita campos extras; `Output*` aceita auxiliares do backend. Na API pública, `raise_on_extra_kwargs` converte erros exclusivamente de kwargs desconhecidos em `TypeError`; os demais erros de validação permanecem `ValidationError`.

## Schemas pydantic

- Para criar ou alterar modelos, ler `CONTRIBUTING.md` > **Schemas pydantic**. O Output deve refletir o parser, com nomes canônicos, sem valores provisórios; métodos stub não recebem schema.
- Os registros de endpoints estão em `tests/schemas/test_schema_coverage.py`. A existência de um schema não comprova seu uso em runtime: conferir o método e a detecção `_is_wired` em `tests/schemas/test_signature_parity.py`.
- A paridade de assinatura tem exceções para infraestrutura, aliases e métodos com `**kwargs`; endpoints reconhecidos como wired são pulados por esse teste. Validar o comportamento público pelos contratos do scraper.

## Docstrings

Ao alterar método público com filtros em `**kwargs`, ler `CONTRIBUTING.md` > **Docstrings de métodos públicos com kwargs** e executar `uv run pytest tests/schemas/test_docstring_parity.py`. O padrão exige filtros sincronizados com o schema, referência ao método principal nos pares `*_download` e registro de novos casos nos testes de paridade.

## Extração de número de páginas/resultados em raspadores HTML

Ao alterar contagens, usar seleção e extração em cascata para os formatos observados nos samples. Consultar `src/juscraper/courts/_esaj/parse.py::cjsg_n_results` para eSAJ e `src/juscraper/utils/pagination.py::extract_count_with_cascade` para o helper compartilhado. O fallback pelo maior número exige evidência do layout; não o ativar por padrão, pois pode capturar anos ou identificadores. Cada formato suportado precisa de sample e teste.

## Worktree e GitHub

- Trabalhar em branch de feature e worktree dedicada. Se a sessão já começou em worktree isolada para a tarefa, reutilizá-la. Caso contrário, criar uma a partir da branch do PR ou de `origin/main`, preservando o checkout existente.
- Remover uma worktree apenas se criada pela própria sessão, sem trabalho pendente e sem vínculo ativo com a ferramenta que gerencia a sessão. Não remover worktrees preexistentes ou gerenciadas pela ferramenta.
- Fazer push para a branch de feature e abrir PR; nunca enviar commits diretamente para `main`.
- Quando o merge estiver autorizado, usar `gh pr merge <n> --merge --delete-branch`: o commit de merge preserva os commits individuais e o limite do PR.
- Notas de revisão no próprio PR usam `gh pr review --comment`; o GitHub não permite aprovação pelo autor.

## Changelog

- Registrar apenas efeitos para quem usa a API pública: funcionalidades, filtros, correções observáveis, breaking changes e deprecações. Deprecações incluem a tabela de aliases. Correção de docstring que orientava o usuário incorretamente também entra.
- Refatorações internas, testes, tooling e documentação sem efeito público não precisam de entrada.
- Seguir as categorias de Keep a Changelog já usadas no arquivo. Novas entradas ficam em `[Unreleased]`, acima das versões publicadas, que são imutáveis.
- Consolidar o mesmo efeito em uma entrada com a lista de tribunais afetados, inclusive em PRs com vários commits. Separar apenas quando o efeito divergir entre tribunais.

## Idiomas

Comentários de PR/issue, revisões, mensagens de commit e docstrings em `src/` ficam em português. Arquivos em `docs/` ficam em inglês por convenção do projeto.
