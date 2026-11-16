# Samples do listar_processos do STM

Respostas cruas do portal à aba de processos (`search_filter_option=feitos`),
arquivadas pelo Wayback Machine; o portal recusa IP de datacenter. O script
`python -m tests.fixtures.capture.stm` regrava os três, de um IP que o portal
aceite.

| Arquivo | Busca | Captura do Wayback |
| --- | --- | --- |
| `por_numero.html` | `7000374-06.2020.7.00.0000` com `search_filter=numero` (1 processo, do STM) | 16/10/2026 |
| `filtro_situacao.html` | pesquisa avançada (`search_filter=busca_avancada`) com `fq_assunto_pesquisa=INCITAMENTO` e `fq_situacao=MOVIMENTO`, com `q=*`, como no link de filtro do portal (2 processos, um deles de Auditoria, com juiz e conselho) | 30/04/2025 |
| `processos_fisicos.html` | `0000028-58.2008.7.01.0101` com `search_filter=numero` (3 processos em papel; dois sem data de autuação e sem endereço no eproc) | 27/03/2024 |

O Wayback tem 59 respostas dessa aba, de 2021 a 2026; o parser lê as 14
conferidas, de todos esses anos.
