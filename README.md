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

## 📊 Implementações

### Tribunais Disponíveis

| Tribunal | Funcionalidades Disponíveis       |
|----------|-----------------------------------|
| TJSP     | cpopg, cposg, cjsg, cjpg          |
| TJES     | cjsg, cjpg                        |
| TJTO     | cjsg, cjpg                        |
| TJAP     | cjsg                              |
| TJBA     | cjsg                              |
| TJCE     | cjsg                              |
| TJDFT    | cjsg                              |
| TJMT     | cjsg                              |
| TJPA     | cjsg                              |
| TJPB     | cjsg                              |
| TJPE     | cjsg                              |
| TJPI     | cjsg                              |
| TJPR     | cjsg                              |
| TJRN     | cjsg                              |
| TJRO     | cjsg                              |
| TJRR     | cjsg                              |
| TJRS     | cjsg                              |
| TJSC     | cjsg                              |

### Agregadores Disponíveis

| Nome      | Funcionalidades                   |
|-----------|-----------------------------------|
| Datajud   | listar_processos                  |
| Jusbr     | cpopg, download_documents         |
| PDPJ      | existe, cpopg, documentos, movimentos, partes, pesquisa, contar, download_documents |

### Notebooks de Exemplo

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
