# juscraper

Raspador de tribunais e outros sistemas relacionados ao poder judiciário.

## Installation

```bash
$ pip install git+https://github.com/jtrecenti/juscraper
```

## Usando o pacote


Uso básico do pacote:

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


### Uso básico

O pacote foi pensado para atender a requisitos básicos de consulta de dados de processos judiciais em alguns tribunais.

Todo tribunal implementado apresenta (sempre que possível) os seguintes métodos:

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

## Pacotes relacionados

Também estamos desenvolvendo o pacote `datajud`, com um propósito um pouco menor, que fornece uma interface para acesso à API do DataJud, uma ferramenta do CNJ para acesso a dados dos processos judiciais.

## Contributing

Interested in contributing? Check out the contributing guidelines. Please note that this project is released with a Code of Conduct. By contributing to this project, you agree to abide by its terms.

## License

`juscraper` was created by Julio Trecenti. It is licensed under the terms of the MIT license.

## Credits

`juscraper` was created with [`cookiecutter`](https://cookiecutter.readthedocs.io/en/latest/) and the `py-pkgs-cookiecutter` [template](https://github.com/py-pkgs/py-pkgs-cookiecutter).
