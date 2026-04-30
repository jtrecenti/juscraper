# Scripts de captura de samples

Scripts manuais que rodam contra os tribunais reais e salvam HTMLs/JSONs crus em
`tests/<tribunal>/samples/<endpoint>/`. Os samples alimentam os testes de
contrato offline (`test_*_contract.py`) via `responses` + `load_sample` ou
`load_sample_bytes`.

Estes scripts **não são rodados pelo pytest**. São ferramentas de manutenção.

## Quando rodar

- Ao adicionar um scraper novo (gera a primeira leva de samples).
- Quando um teste de contrato falha porque o tribunal mudou o layout HTML.
- Periodicamente, em revisão de rotina, para garantir que os samples ainda
  refletem a realidade.

## Como rodar

Da raiz do repositório, com o ambiente dev instalado:

```bash
python -m tests.fixtures.capture.tjac
python -m tests.fixtures.capture.tjal
python -m tests.fixtures.capture.tjam
python -m tests.fixtures.capture.tjce
python -m tests.fixtures.capture.tjms
python -m tests.fixtures.capture.tjdft
python -m tests.fixtures.capture.tjba
python -m tests.fixtures.capture.tjmt
python -m tests.fixtures.capture.tjap
python -m tests.fixtures.capture.tjes
python -m tests.fixtures.capture.tjrs
python -m tests.fixtures.capture.datajud
```

Cada script eSAJ:

1. Faz 3 consultas contra o eSAJ do tribunal (typical com paginação, um
   resultado, zero resultados).
2. Grava os HTMLs em `tests/<tribunal>/samples/cjsg/`.
3. Imprime no stdout quais arquivos escreveu.

## Dependências

- Somente `requests` (já nas deps do projeto).
- Nada de captcha, browser ou auth — os eSAJ do TJAC/TJAL/TJAM/TJCE/TJMS
  aceitam submissões anônimas.

## Convenção de nomes

Para cjsg, os arquivos gerados são:

| Arquivo | Conteúdo |
|---|---|
| `cjsg/post_initial.html` | resposta crua do POST `resultadoCompleta.do` (descartada pelo parser; serve só para o teste mockar o par POST+GET) |
| `cjsg/results_normal_page_01.html` | GET `trocaDePagina.do?pagina=1` para uma busca com múltiplas páginas |
| `cjsg/results_normal_page_02.html` | idem página 2 |
| `cjsg/single_page.html` | GET `?pagina=1` para busca cujos resultados cabem em 1 página (`n_pags == 1`) |
| `cjsg/no_results.html` | GET `?pagina=1` para busca sem resultados |

Ao mudar a convenção, atualizar este README e os contratos em conjunto.

## Re-captura após falha de teste

1. Reproduza a falha e identifique qual sample quebrou (via `pytest -x -s`).
2. Rode o script do tribunal afetado.
3. Revise o `git diff` dos samples para confirmar que a mudança é um upgrade
   de layout legítimo, não ruído.
4. Ajuste o parser ou o teste conforme necessário e commite sample + fix
   juntos.

## Familia 1B (APIs JSON/GraphQL)

Os scripts `tjdft.py`, `tjba.py`, `tjmt.py`, `tjap.py`, `tjes.py` e `tjrs.py`
capturam samples JSON para os contratos da familia 1B. A mesma convencao de
cenarios vale para os endpoints JSON:

| Arquivo | Conteudo |
|---|---|
| `cjsg/results_normal_page_01.json` | primeira pagina de uma busca typical |
| `cjsg/results_normal_page_02.json` | segunda pagina da mesma busca |
| `cjsg/single_page.json` | busca que cabe em uma pagina |
| `cjsg/no_results.json` | busca sem resultados |

Excecoes: TJMT tambem salva `cjsg/config.json` porque o scraper consulta
`config.json` antes da API; TJES tambem salva samples em `cjpg/` porque expoe
`cjpg` alem de `cjsg`.

## Agregadores

### DataJud (CNJ)

`tests/fixtures/capture/datajud.py` captura samples para o contrato de
`DatajudScraper.listar_processos`. O DataJud expoe o indice Elasticsearch
da CNJ via API publica (`api-publica.datajud.cnj.jus.br`). A
`DEFAULT_API_KEY` publicada na documentacao oficial fica embutida em
`aggregators/datajud/client.py` e o script reusa via import — nada de
env vars.

Diferencas vs. familia 1B:

- Auth: header `Authorization: APIKey <key>`.
- POST com body JSON (Elasticsearch DSL).
- Paginacao por **cursor** `search_after` (nao offset). A 2a pagina depende
  do `sort` do ultimo hit da 1a, exigindo `OrderedRegistry` no contrato.

Saida em `tests/datajud/samples/listar_processos/`:

| Arquivo | Conteudo |
|---|---|
| `results_normal_page_01.json` | `tribunal=TJSP` + `tamanho_pagina=2`: exatamente 2 hits, cada um com campo `sort`. |
| `results_normal_page_02.json` | mesma busca + `search_after` do hit final da p1. |
| `single_page.json` | `numero_processo=<CNJ_TJSP>` + `tamanho_pagina=1000`: 1 hit (`< tamanho_pagina` forca break). |
| `no_results.json` | `numero_processo="00000000000000000000"` (estruturalmente valido, inexistente): `hits.hits == []`. |

Saneamento pos-captura: remove `highlight` (defesa) e trunca arrays
residuais de `movimentos`/`movimentacoes` no `_source` — capturas usam
`mostrar_movs=False`, mas o trim e rede de seguranca.

O body Elasticsearch e construido por
`build_listar_processos_payload` em `aggregators/datajud/download.py` —
a mesma funcao usada pelo client em producao. O capture e os contratos
em `tests/datajud/test_listar_processos_*_contract.py` importam dessa
funcao, atendendo a regra 12 do CLAUDE.md (capture e producao falham
juntos quando o body real do scraper muda).
