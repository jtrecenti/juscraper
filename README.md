# juscraper

[![PyPI version](https://badge.fury.io/py/juscraper.svg)](https://badge.fury.io/py/juscraper)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Documentation](https://img.shields.io/badge/docs-available-brightgreen.svg)](https://jtrecenti.github.io/juscraper/)

Raspador de tribunais e outros sistemas relacionados ao poder judiciário brasileiro.

## 📦 Instalação

### Via PyPI (Recomendado)

```bash
pip install juscraper
```

### Com uv

```bash
uv add juscraper
```

### Versão de Desenvolvimento

Para instalar a versão mais recente do repositório:

```bash
pip install git+https://github.com/jtrecenti/juscraper.git
```

## 🚀 Exemplo Rápido

```python
import juscraper as jus

# Criar scraper para o TJSP
tjsp = jus.scraper('tjsp')

# Buscar jurisprudência
dados = tjsp.cjpg('golpe do pix', paginas=range(1, 4))
print(f"Encontrados {len(dados)} resultados")

# Visualizar primeiros resultados
dados.head()
```

<!-- status:inicio -->
## Implementações e status

Status observado no cenário informado, sem garantia de disponibilidade atual. Sem evidência ou após 30 dias, o estado passa a não verificado na próxima geração. A data limite permanece visível entre atualizações. O último relato de falha continua abaixo.

[Critérios e atualização](https://github.com/jtrecenti/juscraper/blob/main/CONTRIBUTING.md#status-dos-raspadores)

### Tribunais

| Fonte | Endpoint | Estado | Verificação | Válido até |
|---|---|---|---|---|
| STF | `listar_decisoes` | Funcionando | 2026-10-03 | 2026-11-02 |
| STF | `contar_decisoes` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJAC | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJAL | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJAM | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJAP | `cjsg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJBA | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJCE | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJDFT | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJES | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJES | `cjpg` | Degradado | 2026-10-03 | 2026-11-02 |
| TJGO | `cjsg` | Não verificado | 2026-10-03 | - |
| TJMG | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJMG | `cposg` | Não verificado | - | - |
| TJMS | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJMT | `cjsg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJPA | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJPB | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJPE | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJPE | `cpopg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJPI | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJPR | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJRJ | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJRN | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJRO | `cjsg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJRR | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJRS | `cjsg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJSC | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJSP | `cpopg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJSP | `cposg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJSP | `cjsg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJSP | `cjpg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TJTO | `cjsg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TJTO | `cjpg` | Indisponível | 2026-10-03 | 2026-11-02 |
| TRF1 | `cpopg` | Funcionando | 2026-10-03 | 2026-11-02 |
| TRF3 | `cpopg` | Não verificado | 2026-10-03 | - |
| TRF5 | `cpopg` | Não verificado | 2026-10-03 | - |
| TRF6 | `cpopg` | Indisponível | 2026-10-03 | 2026-11-02 |

### Agregadores

| Fonte | Endpoint | Estado | Verificação | Válido até |
|---|---|---|---|---|
| Comunica CNJ | `listar_comunicacoes` | Funcionando | 2026-10-03 | 2026-11-02 |
| Datajud | `listar_processos` | Funcionando | 2026-10-03 | 2026-11-02 |
| Falcão | `listar_decisoes` | Indisponível | 2026-10-03 | 2026-11-02 |
| JusBR | `cpopg` | Não verificado | - | - |
| JusBR | `download_documents` | Não verificado | - | - |
| PDPJ | `existe` | Não verificado | - | - |
| PDPJ | `cpopg` | Não verificado | - | - |
| PDPJ | `documentos` | Não verificado | - | - |
| PDPJ | `movimentos` | Não verificado | - | - |
| PDPJ | `partes` | Não verificado | - | - |
| PDPJ | `pesquisa` | Não verificado | - | - |
| PDPJ | `contar` | Não verificado | - | - |
| PDPJ | `download_documents` | Não verificado | - | - |

### Evidências e limitações

#### STF: `listar_decisoes`

Retornou 5 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('stf').listar_decisoes(pesquisa='pejotização', classe='Rcl', paginas=1, tamanho_pagina=5). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L362)

#### STF: `contar_decisoes`

Retornou 52 linhas de total e facetas; o total foi positivo.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('stf').contar_decisoes(pesquisa='pejotização', classe='Rcl'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L469)

#### TJAC: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjac').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L519)

#### TJAL: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjal').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L586)

#### TJAM: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjam').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L653)

#### TJAP: `cjsg`

A busca foi bloqueada pela verificação de segurança e levantou TJAPSecurityCheckError. O bloqueio documentado anteriormente continua presente no cenário testado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjap').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L720) · [Evidência 2](https://github.com/jtrecenti/juscraper/issues/279) · [Evidência 3](https://github.com/jtrecenti/juscraper/pull/282)

Exceção relacionada: juscraper.courts.tjap.exceptions.TJAPSecurityCheckError.

#### TJBA: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjba').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L762)

#### TJCE: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjce').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L823)

#### TJDFT: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjdft').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L890)

#### TJES: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjes').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L962)

#### TJES: `cjpg`

Retornou 20 registros com processo e classe preenchidos, mas ementa e acordao estavam vazios nos 20. A coleta de metadados funcionou; o conteúdo textual não foi confirmado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjes').cjpg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1036)

#### TJGO: `cjsg`

Duas buscas, por direito e dano moral, devolveram DataFrame vazio. As respostas HTTP 200 contêm o formulário de pesquisa, sem resultados identificados. A causa não foi confirmada.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjgo').cjsg(pesquisa='direito', paginas=1); depois jus.scraper('tjgo').cjsg(pesquisa='dano moral', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1112)

#### TJMG: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjmg').cjsg(pesquisa='dano moral presumido', paginas=1, data_julgamento_inicio='2025-01-01', data_julgamento_fim='2025-03-31'). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1214)

#### TJMS: `cjsg`

Retornou 100 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjms').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1299)

#### TJMT: `cjsg`

As duas tentativas receberam HTML na URL de configuração esperada como JSON e terminaram em JSONDecodeError, antes da busca.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjmt').cjsg(pesquisa='direito', paginas=1); depois jus.scraper('tjmt').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1366)

Exceção relacionada: requests.exceptions.JSONDecodeError.

#### TJPA: `cjsg`

Retornou 25 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpa').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1442)

#### TJPB: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpb').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1513)

#### TJPE: `cjsg`

Retornou 5 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpe').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1581)

#### TJPE: `cpopg`

Retornou 1 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpe').cpopg(id_cnj='00963022520218172001'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1651)

#### TJPI: `cjsg`

Retornou 25 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpi').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1816)

#### TJPR: `cjsg`

Retornou 50 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjpr').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L1874)

#### TJRJ: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjrj').cjsg(pesquisa='dano moral', paginas=1, ano_inicio=2024, ano_fim=2024). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2256)

#### TJRN: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjrn').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2342)

#### TJRO: `cjsg`

As duas tentativas terminaram em JSONDecodeError. A resposta HTTP 200 inspecionada contém uma página que declara bloqueio por suspeita de robotização.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjro').cjsg(pesquisa='direito', paginas=1); depois jus.scraper('tjro').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2403)

Exceção relacionada: requests.exceptions.JSONDecodeError.

#### TJRR: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjrr').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2479)

#### TJRS: `cjsg`

As duas buscas devolveram DataFrame vazio. Na repetição, o corpo da resposta contém erro Solr 503: no servers hosting shard: shard2. O retorno vazio não confirma ausência de julgados.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjrs').cjsg(pesquisa='direito', paginas=1); depois jus.scraper('tjrs').cjsg(pesquisa='direito civil', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2544)

#### TJSC: `cjsg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjsc').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2636)

#### TJSP: `cpopg`

Retornou 1 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjsp').cpopg(id_cnj='1000149-71.2024.8.26.0346', method='html'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2704)

#### TJSP: `cposg`

As consultas HTML por dois CNJs retornaram DataFrame vazio. Na segunda, o portal entregou duas páginas de detalhe, mas o parser descartou ambas por ausência do marcador tabelaTodasMovimentacoes.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjsp').cposg(id_cnj='1000149-71.2024.8.26.0346', method='html'); depois jus.scraper('tjsp').cposg(id_cnj='00221752420038260344', method='html'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L2823)

#### TJSP: `cjsg`

Retornou 20 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjsp').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3008)

#### TJSP: `cjpg`

Retornou 10 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjsp').cjpg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3075)

#### TJTO: `cjsg`

A busca foi recusada com HTTP 403 nas três tentativas internas do cliente e terminou em RetryExhaustedError. A causa do bloqueio não foi determinada.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjto').cjsg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3149)

Exceção relacionada: juscraper.core.exceptions.RetryExhaustedError.

#### TJTO: `cjpg`

A busca foi recusada com HTTP 403 nas três tentativas internas do cliente e terminou em RetryExhaustedError. A causa do bloqueio não foi determinada.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('tjto').cjpg(pesquisa='direito', paginas=1). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3207)

Exceção relacionada: juscraper.core.exceptions.RetryExhaustedError.

#### TRF1: `cpopg`

Retornou 1 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('trf1').cpopg(id_cnj='10088283520214013502'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3265)

#### TRF3: `cpopg`

As duas consultas do CNJ de referência retornaram somente id_cnj, sem processo, classe ou movimentações. Não foi possível distinguir ausência de acesso ao processo de incompatibilidade do fluxo de consulta.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('trf3').cpopg(id_cnj='50059460920254036324'); depois jus.scraper('trf3').cpopg(id_cnj='50059460920254036324'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3398)

#### TRF5: `cpopg`

As duas consultas do CNJ de referência retornaram somente id_cnj, sem processo, classe ou movimentações. Não foi possível distinguir ausência de acesso ao processo de incompatibilidade do fluxo de consulta.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('trf5').cpopg(id_cnj='00584573120254058000'); depois jus.scraper('trf5').cpopg(id_cnj='00584573120254058000'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3504)

#### TRF6: `cpopg`

As duas tentativas falharam ao localizar o CAPTCHA esperado. A resposta inspecionada exige JavaScript antes de exibir o conteúdo; o fluxo HTTP do cliente não chegou à consulta.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('trf6').cpopg(id_cnj='10052295520234063801'); depois jus.scraper('trf6').cpopg(id_cnj='10052295520234063801'). Somente os parâmetros informados, sem validar outros processos ou filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L3594)

Exceção relacionada: builtins.RuntimeError.

#### Comunica CNJ: `listar_comunicacoes`

Retornou 5 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado. A primeira tentativa terminou em timeout; a repetição da mesma consulta retornou 5 comunicações.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('comunica_cnj').listar_comunicacoes(pesquisa='resolucao', paginas=1, itens_por_pagina=5, data_disponibilizacao_inicio='2026-09-28', data_disponibilizacao_fim='2026-10-02'); depois jus.scraper('comunica_cnj').listar_comunicacoes(pesquisa='resolucao', paginas=1, itens_por_pagina=5, data_disponibilizacao_inicio='2026-09-28', data_disponibilizacao_fim='2026-10-02'). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L26)

#### Datajud: `listar_processos`

Retornou 1 registros; colunas exigidas e preenchimento mínimo conferidos no cenário informado. A consulta por CNJ funcionou; a tentativa anterior sem CNJ recebeu HTTP 504 e retornou vazio. O estado se limita à consulta por CNJ.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('datajud').listar_processos(tribunal='TJSP', paginas=1, tamanho_pagina=10); depois jus.scraper('datajud').listar_processos(tribunal='TJSP', paginas=1, tamanho_pagina=10, numero_processo='1000413-22.2017.8.26.0415'). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L142)

#### Falcão: `listar_decisoes`

HTTP 429 na primeira chamada, com bloqueio do IP informado pelo servidor por 27.300 segundos. Nenhuma repetição durante o bloqueio. Limitação deste ambiente, sem inferência de indisponibilidade para outros IPs.

Ambiente/cenário: Linux local, Wi-Fi sem VPN ativa; jus.scraper('falcao').listar_decisoes(pesquisa='dano moral', paginas=1, tamanho_pagina=5). Somente a primeira página, sem validação de paginação adicional ou de outros filtros. Versão ou commit testado: 0.4.0; código 91799582d901756b414e7e7eabe774fd3c635ec4.

[Evidência 1](https://github.com/jtrecenti/juscraper/blob/18d506ed586599844a64c81081dcdb73d31112f4/docs/status/2026-10-03.json#L246)

Exceção relacionada: requests.exceptions.HTTPError.

<!-- status:fim -->

#### Autenticação no JusBR e no PDPJ

JusBR e PDPJ usam o mesmo token JWT do SSO do PJe. Com o extra `govbr`, `auth_govbr()` abre o Google Chrome, o Chromium ou o Microsoft Edge instalado na máquina, num perfil temporário, no portal de serviços do PDPJ; a pessoa faz o login no gov.br, o token é capturado e a janela fecha sozinha:

```bash
pip install 'juscraper[govbr]'
```

```python
import juscraper as jus

jusbr = jus.scraper("jusbr")
jusbr.auth_govbr()
```

O token fica em `~/.config/juscraper/pdpj_token.json` (ou em `$XDG_CONFIG_HOME/juscraper/`), legível só pelo dono do arquivo, e as próximas instâncias do JusBR e do PDPJ o carregam sem novo login. Quando o portal entrega refresh token, o access token é renovado sozinho antes de vencer. Se o navegador não for encontrado, informe o executável em `auth_govbr(navegador=...)`. O login exige navegador com janela e não roda no Google Colab nem em CI; nesses ambientes, passe o token em `auth(token)` ou na variável de ambiente `PDPJ_JWT` (o JusBR também aceita `JUSBR_JWT`).

### Notebooks de Exemplo

> [!WARNING]
> **Ambiente de execução:** estes notebooks fazem requisições reais a serviços externos e não têm compatibilidade garantida com o Google Colab. Tribunais podem bloquear ou limitar IPs compartilhados de provedores de nuvem e datacenters, mesmo quando a mesma consulta funciona em uma conexão local. Alguns exemplos também dependem de CAPTCHA, tokens de acesso ou dependências opcionais. A execução local no Jupyter é o ambiente de referência do projeto; uma falha de conexão no Colab não indica, por si só, uma regressão do `juscraper`.

- [Exemplo TJSP](docs/notebooks/tjsp.ipynb)
- [Exemplo TJRS](docs/notebooks/tjrs.ipynb)
- [Exemplo TJPR](docs/notebooks/tjpr.ipynb)
- [Exemplo TJDFT](docs/notebooks/tjdft.ipynb)
- [Exemplo TJAP](docs/notebooks/tjap.ipynb)
- [Exemplo TJBA](docs/notebooks/tjba.ipynb)
- [Exemplo TJCE](docs/notebooks/tjce.ipynb)
- [Exemplo TJES](docs/notebooks/tjes.ipynb)
- [Exemplo TJMT](docs/notebooks/tjmt.ipynb)
- [Exemplo TJPA](docs/notebooks/tjpa.ipynb)
- [Exemplo TJPB](docs/notebooks/tjpb.ipynb)
- [Exemplo TJPE](docs/notebooks/tjpe.ipynb)
- [Exemplo TJPI](docs/notebooks/tjpi.ipynb)
- [Exemplo TJRN](docs/notebooks/tjrn.ipynb)
- [Exemplo TJRO](docs/notebooks/tjro.ipynb)
- [Exemplo TJRR](docs/notebooks/tjrr.ipynb)
- [Exemplo TJSC](docs/notebooks/tjsc.ipynb)
- [Exemplo TJTO](docs/notebooks/tjto.ipynb)
- [Exemplo Datajud](docs/notebooks/datajud.ipynb)
- [Exemplo Jusbr](docs/notebooks/jusbr.ipynb)
- [Exemplo PDPJ](docs/notebooks/pdpj.ipynb)

## Detalhes

O pacote foi pensado para atender a requisitos básicos de consulta de dados de processos judiciais em alguns tribunais.

Os tribunais implementados vão apresentar os seguintes métodos:

- `.cpopg()`: consulta de processos originários do primeiro grau
- `.cposg()`: consulta de processos originários do segundo grau
- `.cjsg()`: consulta de jurisprudência

Os métodos `.cpopg()` e `.cposg()` recebem como *input* um número de processo no padrão CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO), com ou sem separadores, e retorna um `dict` com tabelas dos elementos do processo (dados básicos, partes, movimentações, entre outros específicos por tribunal).

O método `.cjsg()` recebe como *input* parâmetros de busca de jurisprudência (que variam por tribunal) e retorna uma tabela com os resultados da consulta. Boa parte dos tribunais apresentam limites de paginação ao realizar buscas muito gerais (i.e. que retornam muitos resultados). Nesses casos, o método dará um aviso ao usuário com o número total de resultados, confirmando se deseja mesmo baixar todos os resultados.

### Controle de arquivos

Caso o usuário queira controlar o armazenamento dos arquivos brutos dos processos, deverá implementar as seguintes funções:

- `.cpopg_download()`: baixa o arquivo bruto da consulta de processos originários do primeiro grau, retornando o caminho do arquivo baixado.
- `.cpopg_parse()`: lê e processa um arquivo bruto ou arquivos dentro de uma pasta resultantes da consulta de processos, retornando o `dict` com tabelas dos elementos do processo, como na função `.cpopg()`.

O mesmo se aplica para as funções `.cposg_download()` e `.cposg_parse()`.

Observação: Em alguns tribunais ou situações específicas, a consulta a um processo pode gerar vários arquivos brutos. Por esse motivo, toda consulta cria uma pasta com o número do processo e, dentro dessa pasta, cria os arquivos correspondentes ao download.

Para a função `.cjsg()`, uma consulta pode resultar

### Diferenciais do `juscraper`

- Controle sobre arquivos brutos: o pacote fornece uma interface para baixar e armazenar arquivos brutos (HTML e JSON, por exemplo) dos processos. Por padrão, no entanto, esses arquivos brutos são descartados assim que os dados são processados, com exceção dos arquivos que apresentaram algum problema na leitura.

### Restrições

Por ser um pacote bastante complexo e também nichado, adotamos algumas restrições sobre o escopo do pacote para que seja simples de usar.

- O pacote não utiliza paralelização, ou seja, se o usuário tiver interesse em realizar requisições em paralelo, deverá desenvolver as adaptações necessárias.
- O pacote não possui absolutamente todas as funcionalidades que os tribunais permitem. Se o usuário tiver interesse em consultar processos em mais tribunais, deverá desenvolver os raspadores.

### Por que não um `juscraper` no R?

O pacote `juscraper` foi criado em python inicialmente com o propósito de ser usado em aulas de Ciência de Dados no Direito do Insper. Portanto, não houve incentivo nem fôlego para criar uma alternativa em R.

Já existem soluções usando o R para esses raspadores, como os pacotes `tjsp` e `stj`, mas a comunidade convergiu para soluções em python, que atualmente são mais populares.

### Observação sobre o parâmetro `paginas`

O parâmetro `paginas` é **1-based** em todos os scrapers. Ao utilizar as funções de download, `range(1, n+1)` faz o download das páginas 1 até n, ou seja, `range(1, 4)` baixa as páginas 1, 2 e 3. Onde suportado, passar um inteiro (ex: `paginas=3`) é equivalente a `range(1, 4)`.

Exemplo de uso:

```python
scraper.cjsg_download(pesquisa="dano moral", paginas=range(1, 6))  # Baixa as páginas 1 a 5
scraper.cjpg_download(pesquisa="contrato", paginas=range(1, 3))    # Baixa as páginas 1 e 2
```

## Instalação em desenvolvimento

Para instalar o pacote em modo desenvolvimento, siga os passos abaixo:

```bash
# Clone o repositório (caso ainda não tenha feito)
$ git clone https://github.com/jtrecenti/juscraper.git
$ cd juscraper

# Instale as dependências e o pacote em modo editável
$ uv pip install -e .
```

## Contribuição

Interessado em contribuir? Verifique as diretrizes de contribuição. Por favor, note que este projeto é lançado com um Código de Conduta. Ao contribuir para este projeto, você concorda em obedecer às suas termos.

## Licença

`juscraper` foi criado por Julio Trecenti. Está licenciado sob os termos da licença MIT.

## Créditos

`juscraper` foi criado com [`cookiecutter`](https://cookiecutter.readthedocs.io/en/latest/) e o [template](https://github.com/py-pkgs/py-pkgs-cookiecutter) `py-pkgs-cookiecutter`.
