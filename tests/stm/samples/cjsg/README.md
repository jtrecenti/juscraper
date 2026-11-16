# Samples do cjsg do STM

O WAF do portal recusa o IP da máquina em que o raspador foi escrito
(datacenter, fora do Brasil), e por isso os samples não saíram de
`tests/fixtures/capture/stm.py`. São respostas reais do portal, arquivadas
pelo Wayback Machine e baixadas sem alteração (`web.archive.org/web/<data>id_/<url>`):

| Arquivo | Captura | URL no portal |
| --- | --- | --- |
| `results_normal_page_01.html` | 08/04/2025 (`20250408134131`) | `consulta.php?search_input=&search_input="corrupção ativa"&search_filter_option=jurisprudencia&q="corrupção ativa"&q_or="corrupção ativa"&search_filter=ementa&start=0&rows=100` |
| `results_normal_page_02.html` | 13/04/2025 (`20250413104321`) | a mesma busca, com `start=100&rows=100` |
| `single_page.html` | 29/10/2025 (`20251029034157`) | `consulta.php?search_input=&search_input=0000088-44.2014.7.07.0007&search_filter_option=jurisprudencia&q=0000088-44.2014.7.07.0007&q_or=0000088-44.2014.7.07.0007&search_filter=numero` |
| `no_results.html` | 29/06/2024 (`20240629164921`) | `index.php?search_filter_option=jurisprudencia&search_filter=numero`, para onde `consulta.php` redireciona (HTTP 302) a busca sem resultados |

`waf_rejected.html` é a resposta direta do portal, em 16/11/2026, a um pedido
de IP de datacenter: HTTP 200 com a página "Request Rejected".

De um IP que o WAF aceite, `python -m tests.fixtures.capture.stm` regrava
os quatro primeiros a partir do portal.
