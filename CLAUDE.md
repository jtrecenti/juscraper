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

- Testes ficam em `tests/` com subdiretorios por tribunal (`tests/tjdft/`, `tests/tjpr/`, etc.)
- Cada subdiretorio de testes precisa ter um `__init__.py` para o pytest descobrir os testes
- Testes que acessam servidores externos devem ser marcados com `@pytest.mark.integration`
- Rodar apenas testes rapidos: `pytest -m "not integration"`
- Rodar todos os testes: `pytest`
- `--strict-markers` esta ativo — todo marker deve ser registrado no `pyproject.toml`

## Convencao de paginacao

- O parametro `paginas` e sempre 1-based em todos os scrapers
- range(1, 4) baixa paginas 1, 2 e 3
- Onde suportado, paginas=3 (int) e equivalente a range(1, 4)
- paginas=None baixa todas as paginas disponiveis

## Regras de workflow no GitHub

- Nunca tentar aprovar o proprio PR (`gh pr review --approve` falha para o autor do PR)
- Usar `gh pr review --comment` para deixar notas de revisao nos proprios PRs
- Sempre fazer push para uma branch de feature e abrir PR — nunca fazer push direto na main

## Changelog

- Seguimos o padrao [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
- Toda mudanca relevante deve ser registrada em `CHANGELOG.md` sob `[Unreleased]`
- Categorias: Added, Changed, Deprecated, Removed, Fixed, Security

## Documentacao

- Documentacao do projeto (em `docs/`) deve ser escrita em ingles
- Portugues causa problemas de encoding no build do site (Quarto + GitHub Actions)
