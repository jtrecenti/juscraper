# CLAUDE.md

juscraper é uma biblioteca Python para coletar dados de tribunais e agregadores brasileiros. A entrada pública é `juscraper.scraper()`; as implementações ficam em `src/juscraper/courts/` (famílias compartilhadas em pacotes com `_`, como `_esaj/` e `_trf/`) e `src/juscraper/aggregators/`. As regras abaixo valem para qualquer mudança; o detalhe está em `CONTRIBUTING.md` > **Internal Dev Guide**.

## Desenvolvimento

```bash
uv sync --extra dev                         # ambiente + instalação editável
uv run pre-commit install                   # hooks de lint e typecheck
uv run pytest tests/<área afetada>          # só os testes afetados; a suíte inteira roda no CI
uv run pre-commit run --files <arquivos>    # antes de concluir uma alteração
```

- Em mudança de API ou schema, incluir `tests/schemas/` nos testes afetados, além do `tests/<sigla>/` do tribunal (as regras de um tribunal só ficam em `tests/<sigla>/test_cjsg_schema.py`).
- Testes importam o pacote instalado, sem alterar `sys.path`.
- O typecheck que reprova é o hook `mypy` do pre-commit (`uv run pre-commit run mypy --all-files`); `uv run mypy src` usa outra versão e não é gate.
- `# noqa` só para exceção deliberada, com código completo e justificativa. Dívida de lint se corrige no código, não em `# noqa` nem em `ruff.toml`.

## Arquitetura

- **Regra de generalização:** mover para `_<familia>/` ou criar mixin/base só com **2+ ocorrências concretas**. Duplicar com 1 caso é mais barato que abstrair errado.
- Nas famílias, acomodar diferenças por hooks/atributos ou manter scraper próprio; nunca `if tribunal == "X"` no código compartilhado.
- A seleção `paginas` chega ao raspador como `Paginas` (opaca, sem laço nem `len`) e só é lida pelos helpers de `utils/pagination.py`; o laço de páginas comum é `baixar_paginas_pedidas`, e o que muda entre portais entra nele como gancho (`CONTRIBUTING.md` > **Seleção de páginas**).

## Testes

- Mudança em parser exige sample de resposta real e teste do formato afetado. Formato que aparece em mais de um tribunal da família precisa de sample de cada um: procurar antes nos samples existentes e gravar o que faltar pelo script de `tests/fixtures/capture/<sigla>.py`.
- Teste que acessa rede leva o marker `integration`. Ao mexer num tribunal, rodar a integração dele localmente antes do PR.
- Antes de refatorar um tribunal, seus contratos devem passar. Wiring de schema vai em PR separado do PR de contratos; se a issue de contratos deixar o wiring em aberto, abrir follow-up.

## Antes de mexer em

| Área | Ler |
| --- | --- |
| Novo raspador | `CONTRIBUTING.md` > **Adding a new tribunal** (e **Adding an eSAJ tribunal**) |
| Parâmetros, aliases, datas, paginação | `docs/api-conventions.qmd` e `CONTRIBUTING.md` > **Política de deprecação** |
| Schemas pydantic | `CONTRIBUTING.md` > **Schemas pydantic** |
| Docstrings com filtros em `**kwargs` | `CONTRIBUTING.md` > **Docstrings de métodos públicos com kwargs** |
| HTTP, retry, falhas por linha, coleta parcial | `CONTRIBUTING.md` > **Falhas HTTP, falhas por linha e coleta parcial** |
| Laço de páginas, `paginas` explícito | `CONTRIBUTING.md` > **Seleção de páginas** |
| Contagem de páginas/resultados em HTML | `CONTRIBUTING.md` > **Contagem de páginas e resultados em HTML** |
| Samples, integração, CI | `CONTRIBUTING.md` > **Tests** |
| Lint e complexidade | `CONTRIBUTING.md` > **Política de lint e adoção gradual** e **Complexidade de código (lizard + complexipy)** |

## API pública e changelog

- Preservar nomes canônicos e aliases deprecados. Quebra deliberada segue `CONTRIBUTING.md` > **Política de deprecação**.
- `CHANGELOG.md` registra só efeitos para quem usa a API pública, em `[Unreleased]` (regras em `CONTRIBUTING.md` > **Changelog**). PR que muda `src/juscraper/` sem efeito público leva a etiqueta `sem-changelog`.

## Worktree e GitHub

- Trabalhar em branch de feature e worktree dedicada: reutilizar a da sessão, se houver; senão, criar a partir da branch do PR ou de `origin/main`, preservando o checkout existente. Remover só a worktree criada pela própria sessão, sem trabalho pendente e sem vínculo com a ferramenta que gerencia a sessão.
- Nunca enviar commits para `main`: push na branch e PR. Merge autorizado: `gh pr merge <n> --merge --delete-branch`. Nota de revisão no próprio PR: `gh pr review --comment`.
- Commits, PRs, comentários de issue, revisões e docstrings de `src/` em português; arquivos de `docs/` em inglês. Commits e PRs levam a área no início (`TJMT: ...`, `fix(tjro): ...`).
