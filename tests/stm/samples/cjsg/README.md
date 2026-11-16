# Samples do cjsg do STM

Respostas cruas do portal, gravadas em 16/11/2026 por
`python -m tests.fixtures.capture.stm`, de um IP residencial no Brasil:

| Arquivo | Busca |
| --- | --- |
| `results_normal_page_01.html` | `"corrupção ativa"` na ementa, `start=0&rows=100` (205 documentos) |
| `results_normal_page_02.html` | a mesma busca, `start=100&rows=100` |
| `results_normal_page_03.html` | a mesma busca, `start=200&rows=100` (5 documentos) |
| `single_page.html` | `0000088-44.2014.7.07.0007` com `search_filter=numero` |
| `no_results.html` | `juscraper_probe_zero_hits_xyzqwe`: `consulta.php` responde 302 para `index.php?search_filter_option=jurisprudencia&search_filter=ementa`, que mostra "Nenhum documento encontrado"; o arquivo é a página final |
| `campo_tudo.html` | `"corrupção ativa"` com `search_filter=tudo` e `fq_ministro_relator=CARLOS VUYK DE AQUINO` |
| `campo_referencia_legislativa.html` | `290` com `search_filter=referencia_legislativa` e o mesmo relator |
| `avancada_datas.html` | pesquisa avançada (`search_filter=busca_avancada`) com `q=(data_decisao:[2010-01-01T00:00:00.000Z TO 2022-06-08T23:59:59.000Z])` e `fq_ministro_relator=CLAUDIO PORTUGAL DE VIVEIROS` (1 documento) |

`waf_rejected.html` não sai do script: é a resposta direta do portal, em
16/11/2026, a um pedido de IP de datacenter fora do Brasil (HTTP 200 com a
página "Request Rejected").

Antes da prova ao vivo, os samples eram respostas do portal arquivadas pelo
Wayback Machine (2024 e 2025), com o mesmo template.
