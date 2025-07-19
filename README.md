# juscraper

Raspador de tribunais e outros sistemas relacionados ao poder judiciário.

## 🚧 Em desenvolvimento 🚧

O pacote ainda não está disponível no PyPI. Instale a versão em desenvolvimento com:

```bash
pip install git+https://github.com/jtrecenti/juscraper.git
```

## Implementações

### Tribunais Disponíveis

| Tribunal | Funcionalidades Disponíveis       |
|----------|-----------------------------------|
| TJSP     | cpopg, cposg, cjsg, cjpg, acordao |
| TJRS     | cjsg                              |
| TJPR     | cjsg                              |
| TJDFT    | cjsg                              |

### Agregadores Disponíveis

| Nome      | Funcionalidades                   |
|-----------|-----------------------------------|
| Datajud   | listar_processos                  |
| Jusbr     | cpopg, download_documents         |

### Notebooks de Exemplo

- [Exemplo TJSP](docs/notebooks/tjsp.ipynb)
- [Exemplo TJRS](docs/notebooks/tjrs.ipynb)
- [Exemplo TJPR](docs/notebooks/tjpr.ipynb)
- [Exemplo TJDFT](docs/notebooks/tjdft.ipynb)
- [Exemplo Datajud](docs/notebooks/datajud.ipynb)
- [Exemplo Jusbr](docs/notebooks/jusbr.ipynb)

## Como usar

```python
import juscraper as jus

tjsp = jus.scraper('tjsp')
dados_cjpg = tjsp.cjpg('league of legends', paginas=range(1,3))

dados_cjpg.head(3)
```

```md
Total de páginas: 6
Paginas a serem baixadas: [1, 2]
Baixando documentos: 100%|██████████| 2/2 [00:01<00:00,  1.38it/s]
Processando documentos: 100%|██████████| 2/2 [00:00<00:00, 29.39it/s]
```

        cd_processo	id_processo	classe	assunto	magistrado	comarca	foro	vara	data_disponibilizacao	decisao
        0	2P000BYIO0000	1001296-06.2024.8.26.0097	Procedimento Comum Cível	Práticas Abusivas	ANDRÉ FREDERICO DE SENA HORTA	Buritama	Foro de Buritama	1ª Vara	17/03/2025	SENTENÇA\n\n\n\nProcesso Digital nº:\t1001296-...
        1	2S001UFAG0000	1059728-09.2024.8.26.0100	Procedimento Comum Cível	Práticas Abusivas	Ricardo Augusto Ramos	SÃO PAULO	Foro Central Cível	7ª Vara Cível	25/11/2024	SENTENÇA\n\n\n\nProcesso Digital nº:\t1059728-...
        2	2S001TWI60000	1041014-98.2024.8.26.0100	Procedimento Comum Cível	Práticas Abusivas	LUCIANA BIAGIO LAQUIMIA	SÃO PAULO	Foro Central Cível	17ª Vara Cível	28/10/2024	SENTENÇA\n\n\n\nProcesso Digital nº:\t1041014-...

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

### Diferenciais do `juscraper`:

- Controle sobre arquivos brutos: o pacote fornece uma interface para baixar e armazenar arquivos brutos (HTML e JSON, por exemplo) dos processos. Por padrão, no entanto, esses arquivos brutos são descartados assim que os dados são processados, com exceção dos arquivos que apresentaram algum problema na leitura.

### Restrições:

Por ser um pacote bastante complexo e também nichado, adotamos algumas restrições sobre o escopo do pacote para que seja simples de usar.

- O pacote não utiliza paralelização, ou seja, se o usuário tiver interesse em realizar requisições em paralelo, deverá desenvolver as adaptações necessárias.
- O pacote não possui absolutamente todas as funcionalidades que os tribunais permitem. Se o usuário tiver interesse em consultar processos em mais tribunais, deverá desenvolver os raspadores.

### Por que não um `juscraper` no R?

O pacote `juscraper` foi criado em python inicialmente com o propósito de ser usado em aulas de Ciência de Dados no Direito do Insper. Portanto, não houve incentivo nem fôlego para criar uma alternativa em R.

Já existem soluções usando o R para esses raspadores, como os pacotes `tjsp` e `stj`, mas a comunidade convergiu para soluções em python, que atualmente são mais populares.

### Observação sobre o parâmetro `paginas`

Ao utilizar as funções de download `cjsg_download` e `cjpg_download`, o parâmetro `paginas` deve ser um objeto `range`. Por padrão, `range(0, n)` fará o download das páginas 1 até n (inclusive), ou seja, `range(0, 3)` baixa as páginas 1, 2 e 3. Isso torna o comportamento mais intuitivo para o usuário.

Exemplo de uso:

```python
scraper.cjsg_download(pesquisa="dano moral", paginas=range(0, 5))  # Baixa as páginas 1 a 5
scraper.cjpg_download(pesquisa="contrato", paginas=range(0, 2))    # Baixa as páginas 1 e 2
```

## Instalação em desenvolvimento

Para instalar o pacote em modo desenvolvimento, siga os passos abaixo (necessário Python >= 3.12):

```bash
# Clone o repositório (caso ainda não tenha feito)
$ git clone https://github.com/jtrecenti/juscraper.git
$ cd juscraper

# Instale as dependências e o pacote em modo editável
$ uv pip install -e .
```

Saída esperada:

```
(juscraper) PS C:\Users\julio\OneDrive\Documentos\insper\juscraper> uv pip install -e .
>>
Resolved 56 packages in 255ms
      Built juscraper @ file:///C:/Users/julio/OneDrive/Documentos/insper/juscraper
Prepared 1 package in 7.26s
Installed 1 package in 39ms
 + juscraper==0.1.0 (from file:///C:/Users/julio/OneDrive/Documentos/insper/juscraper)
(juscraper) PS C:\Users\julio\OneDrive\Documentos\insper\juscraper>
```

## Contributing

Interested in contributing? Check out the contributing guidelines. Please note that this project is released with a Code of Conduct. By contributing to this project, you agree to abide by its terms.

## License

`juscraper` was created by Julio Trecenti. It is licensed under the terms of the MIT license.

## Credits

`juscraper` was created with [`cookiecutter`](https://cookiecutter.readthedocs.io/en/latest/) and the `py-pkgs-cookiecutter` [template](https://github.com/py-pkgs/py-pkgs-cookiecutter).
