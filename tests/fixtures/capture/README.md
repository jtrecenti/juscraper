# Scripts de captura de samples

Scripts manuais que rodam contra os tribunais reais e salvam HTMLs crus em
`tests/<tribunal>/samples/<endpoint>/`. Os samples alimentam os testes de
contrato offline (`test_*_contract.py`) via `responses` + `load_sample_bytes`.

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
```

Cada script:

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
