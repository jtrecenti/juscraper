"""Raspador do Tribunal Regional Federal da 3ª Região (TRF3).

Consulta processual pública do PJe do TRF3, pela API JSON que a aplicação
``pje1g-consultapublica.trf3.jus.br`` (1º grau) e
``pje2g-consultapublica.trf3.jus.br`` (2º grau) consome. O endereço JSF antigo
(``pje1g.trf3.jus.br/pje/ConsultaPublica/listView.seam``) chegou a redirecionar
para essa aplicação, por isso o TRF3 deixou a família ``_trf``, que segue
servindo TRF5 e TJPE. O fluxo da consulta é o da família
:mod:`juscraper.courts._pje_api`, que o TRF1 também usa; as instalações do
TRF3 ficam em :mod:`juscraper.courts.trf3.download`. As requisições à consulta passam pelo
``curl_cffi`` com TLS do Chrome (extra ``juscraper[tls]``,
:mod:`juscraper.courts.trf3._tls`).

``cjsg`` pesquisa jurisprudência em ``web.trf3.jus.br/jurisprudencia``, uma
aplicação ASP.NET separada do PJe, também atrás do Akamai. Não usa a sessão
da consulta processual: cada busca abre a sua ``requests.Session`` com
cabeçalhos próprios e, com o extra ``juscraper[tls]`` instalado, o mesmo
transporte com TLS do Chrome. Do raspador usa o retry de ``HTTPScraper``, o
``sleep_time`` do construtor e o perfil HTTP ``perfis_http["cjsg"]``. O código
fica em :mod:`.cjsg_download`, :mod:`.cjsg_parse` e :mod:`.cjsg_schemas`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd
import requests

from ...core.http import RequestPolicy
from ...schemas import CnjInputBase
from ...utils.params import apply_input_pipeline_search
from .._pje_api.base import PJeAPIScraper
from .._pje_api.download import AplicacaoPJe
from ._tls import montar_tls_navegador
from .cjsg_download import PERFIL_CJSG, build_cjsg_session, cjsg_download_manager
from .cjsg_parse import cjsg_parse_manager
from .cjsg_schemas import InputCJSGTRF3, validar_combinacoes
from .download import APLICACAO_1G, APLICACAO_2G, BASE_URL_1G, BASE_URL_2G, TRIBUNAL
from .schemas import InputCpopgTRF3, InputCposgTRF3

# Parte das requisições fica sem resposta atrás do Akamai até o cliente
# desistir; uma nova tentativa costuma responder em menos de um segundo. Por
# isso o timeout de leitura é curto e timeout e erro de conexão são retentados.
_PERFIS_HTTP: dict[str, RequestPolicy] = {
    "api": RequestPolicy(
        timeout=(10.0, 20.0),
        max_retries=4,
        retry_on_timeout=True,
        retry_on_connection_error=True,
        expect_json=True,
    ),
    "documento": RequestPolicy(
        timeout=(10.0, 60.0),
        max_retries=3,
        retry_on_timeout=True,
        retry_on_connection_error=True,
    ),
    # Busca de jurisprudência: parte das requisições ao portal também fica
    # pendurada atrás do Akamai; o timeout curto com nova tentativa recupera
    # esses casos em segundos.
    PERFIL_CJSG: RequestPolicy(
        timeout=(10, 60),
        max_retries=4,
        retry_on_timeout=True,
        retry_on_connection_error=True,
    ),
}


class TRF3Scraper(PJeAPIScraper):
    """Raspador do TRF3: consulta pública do PJe (1º e 2º grau) e jurisprudência.

    ``cpopg`` e ``cposg`` consultam a API JSON da consulta pública do PJe.
    ``cjsg`` pesquisa ``web.trf3.jus.br/jurisprudencia``, sistema separado com
    sessão própria.

    Perfis HTTP ajustáveis com ``politica=``: ``"api"`` (busca e detalhe,
    timeout de leitura de 20 s, 4 tentativas), ``"documento"`` (PDF das
    peças, timeout de leitura de 60 s, 3 tentativas) e ``"cjsg"`` (busca de
    jurisprudência, timeout de leitura de 60 s, 4 tentativas).
    """

    #: Raiz da aplicação de 1º grau, usada pelo ``cpopg``.
    BASE_URL: str = BASE_URL_1G
    #: Raiz da aplicação de 2º grau, usada pelo ``cposg``.
    BASE_URL_2G: str = BASE_URL_2G
    TRIBUNAL_NAME: str = TRIBUNAL
    APLICACAO_1G: ClassVar[AplicacaoPJe] = APLICACAO_1G
    APLICACAO_2G: ClassVar[AplicacaoPJe] = APLICACAO_2G
    INPUT_CPOPG: type[CnjInputBase] = InputCpopgTRF3
    INPUT_CPOSG: type[CnjInputBase] = InputCposgTRF3
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = _PERFIS_HTTP

    def _configure_session(self, session: requests.Session) -> None:
        """Cabeçalhos de uma chamada XHR do Chrome e TLS de navegador nas duas aplicações da consulta.

        O ``cjsg`` usa sessão própria e não passa por aqui.
        """
        super()._configure_session(session)
        montar_tls_navegador(session, [self.APLICACAO_1G.api_url, self.APLICACAO_2G.api_url])

    def _alvo(self, endpoint: str) -> tuple[type[CnjInputBase], AplicacaoPJe]:
        """Schema de entrada e instalação que atendem ``cpopg`` ou ``cposg``."""
        if endpoint == "cposg":
            return self.INPUT_CPOSG, self.APLICACAO_2G
        return self.INPUT_CPOPG, self.APLICACAO_1G

    def cpopg(
        self,
        id_cnj: str | list[str],
        *,
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 1º grau na consulta pública do PJe do TRF3.

        Exige o extra ``juscraper[tls]``. Limitação conhecida: em 15/11/2026 a
        API do 1º grau respondia 403 do Akamai a qualquer cliente, inclusive
        navegadores, e o ``cpopg`` saía ``bloqueio_anti_bot`` no primeiro
        pedido. O :meth:`cposg` não tinha esse bloqueio.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo, logo depois dos dados do processo. Só por nome.
                Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.
            **kwargs: Nenhum outro argumento é aceito; nome desconhecido
                levanta ``TypeError``.

        Returns:
            DataFrame com uma linha por CNJ e as colunas ``id_cnj``,
                ``processo``, ``classe``, ``assunto``, ``data_distribuicao``
                (``DD/MM/AAAA``), ``orgao_julgador``, ``orgao_julgador_colegiado``,
                ``jurisdicao``, ``endereco_orgao``, ``polo_ativo``,
                ``polo_passivo``, ``outros_interessados``, ``movimentacoes``,
                ``documentos`` e ``motivo_falha``. Com ``download_pecas=True``,
                ganha ``pecas``, a lista de caminhos gravados, e
                ``pecas_falhas``, as peças que não puderam ser baixadas, cada
                uma como ``{"id": <id da peça>, "motivo_falha": <motivo>}``; as
                falhas de peça saem num ``UserWarning`` próprio ao fim e não
                mudam ``motivo_falha`` do processo, salvo o bloqueio anti-bot
                (abaixo).

                ``motivo_falha`` é ``None`` quando a consulta respondeu,
                inclusive para o CNJ que a consulta pública não devolve
                (inexistente ou em segredo de justiça), que sai como linha só
                com ``id_cnj``. Quando a consulta de um CNJ falha, a linha sai
                só com ``id_cnj`` e o motivo, no vocabulário de
                :data:`juscraper.core.failures.MOTIVOS_FALHA` (erro HTTP ou de
                rede na busca ou em ``/dados`` depois das tentativas;
                ``resposta_inesperada`` para resposta fora do formato
                esperado), e o lote segue. As falhas entram num único
                ``UserWarning`` ao fim
                (:class:`~juscraper.core.exceptions.BloqueioAntiBotWarning`
                quando há bloqueio anti-bot).

                Um bloqueio do Akamai vale para a sessão inteira: o lote para
                no CNJ bloqueado, sem novos pedidos, e ele e os seguintes saem
                com ``bloqueio_anti_bot``. As linhas anteriores são
                preservadas, com as peças já gravadas. O processo bloqueado
                nas peças sai com os dados lidos, as peças já gravadas e
                ``bloqueio_anti_bot``; a bloqueada e as seguintes entram em
                ``pecas_falhas``. Aguarde alguns minutos ou troque de IP e peça
                de novo só as linhas com ``motivo_falha``. Um erro ao gravar
                uma peça (disco cheio, sem permissão) para as peças daquele
                processo do mesmo jeito, com ``resposta_inesperada``, e o lote
                segue.

        Raises:
            TypeError: Kwarg desconhecido.
            ImportError: O extra ``juscraper[tls]`` (``curl_cffi``) não está
                instalado.

        See Also:
            :class:`InputCpopgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cpopg", id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs)

    def cposg_download(self, id_cnj: str | list[str], **kwargs: Any) -> list[dict[str, Any] | None]:
        """Baixa os envelopes JSON de 2º grau de cada CNJ, sem parsear.

        Mesmo retorno e mesmos avisos de :meth:`cpopg_download`, consultando a
        aplicação de 2º grau. Os argumentos são os de :meth:`cposg`;
        ``download_pecas`` e ``diretorio`` passam pela validação e são
        ignorados, porque este método não baixa peças.
        """
        return self._download("cposg", "cposg_download", id_cnj, **kwargs)

    def cposg_parse(self, brutos: list[dict[str, Any] | None], id_cnj_list: list[str]) -> pd.DataFrame:
        """Transforma a saída de :meth:`cposg_download` num DataFrame, uma linha por CNJ.

        Como :meth:`cpopg_parse`, sem a coluna ``motivo_falha``.
        """
        return self._parse(brutos, id_cnj_list, "cposg_parse")

    def cposg(
        self,
        id_cnj: str | list[str],
        *,
        download_pecas: bool = False,
        diretorio: str | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Consulta processos de 2º grau na consulta pública do PJe do TRF3.

        O CNJ do recurso costuma ser o mesmo do processo de origem; a consulta
        de 2º grau devolve o recurso (apelação, agravo, remessa) que tramita
        no tribunal com esse número. Se a busca devolver mais de um processo
        com o número pedido, só o primeiro é consultado, e o logger
        ``juscraper.trf3`` avisa quantos a busca devolveu; nas consultas
        observadas a busca devolveu no máximo um. Exige o extra
        ``juscraper[tls]``.

        Args:
            id_cnj: CNJ único ou lista, com ou sem máscara.
            download_pecas: Se ``True``, baixa o PDF de cada documento listado
                no processo, logo depois dos dados do processo. Só por nome.
                Default ``False``.
            diretorio: Onde gravar as peças, em ``<diretorio>/<cnj>/<id>.pdf``.
                Quando omitido, usa ``download_path`` do construtor.
            **kwargs: Nenhum outro argumento é aceito; nome desconhecido
                levanta ``TypeError``.

        Returns:
            DataFrame com as mesmas colunas e o mesmo tratamento de falhas de
                :meth:`cpopg`. No 2º grau, ``orgao_julgador_colegiado`` traz a
                turma, e o CNJ sem recurso no 2º grau sai como linha só com
                ``id_cnj`` e ``motivo_falha`` ``None``.

        Raises:
            TypeError: Kwarg desconhecido.
            ImportError: O extra ``juscraper[tls]`` (``curl_cffi``) não está
                instalado.

        See Also:
            :class:`InputCposgTRF3`: schema dos argumentos aceitos.
        """
        return self._consulta("cposg", id_cnj, download_pecas=download_pecas, diretorio=diretorio, **kwargs)

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Pesquisa jurisprudência no portal do TRF3 (``web.trf3.jus.br/jurisprudencia``).

        Cada chamada abre uma sessão própria no portal, executa a busca e lê
        a lista resumida, que já traz ementa e inteiro teor de cada documento.
        Custa três requisições fixas (abertura da aba, ``POST`` da busca e
        ``GET`` do redirect que traz a página 1) e uma por página adicional,
        com ``sleep_time`` entre páginas.

        Com o extra ``juscraper[tls]`` instalado, as requisições saem com o
        TLS do Chrome, como no :meth:`cpopg`. O extra é opcional aqui: sem
        ele, a busca usa o ``requests``, que o Akamai do portal atende de IP
        residencial, mas deixa sem resposta até o timeout de IP de
        datacenter (medido em 15/11/2026).

        Args:
            pesquisa (str | None): Texto da pesquisa livre, com os operadores do
                portal (operador padrão ``e``). Pode ficar vazio quando outro
                critério for informado.
            paginas (int | list | range | None): Páginas 1-based; ``None`` baixa
                todas. Páginas além do total são ignoradas sem requisição.
            **kwargs: Filtros aceitos por :class:`InputCJSGTRF3`:

                * ``base`` (str): ``"acordaos"`` (default; acórdãos do TRF3),
                  ``"turmas_recursais"`` (acórdãos das Turmas Recursais dos
                  JEFs), ``"monocraticas"`` (decisões monocráticas do TRF3) ou
                  ``"monocraticas_turmas_recursais"`` (decisões monocráticas
                  das Turmas Recursais).
                * ``numero_processo`` (str): Número do processo, com ou sem
                  máscara.
                * ``relator`` (str): Nome do relator ou do relator para o
                  acórdão, como o portal indexa (ex.: ``"NERY JUNIOR"``, a
                  forma do dropdown do formulário). O portal casa nomes
                  parciais.
                * ``classe`` (str): Classe como no dropdown, com sigla (ex.:
                  ``"AI - AGRAVO DE INSTRUMENTO"``).
                * ``orgao_julgador`` (str): Órgão julgador, pelo rótulo do
                  dropdown do formulário (``"3ª Turma"``,
                  ``"11ª Turma Recursal da Seção Judiciária de São Paulo"``)
                  ou pelo nome indexado da opção (``"TERCEIRA TURMA"``,
                  ``"11ª TURMA RECURSAL DE SÃO PAULO"``), sem diferença de
                  caixa e de espaços. O valor da coluna ``orgao_julgador``
                  do resultado também serve: "1a. seção" vira "1A", como no
                  formulário, então ``"QUINTA TURMA - 1A. SEÇÃO"`` casa com
                  a opção ``QUINTA TURMA - 1a. SEÇÃO``. A busca manda o par
                  que o navegador mandaria, rótulo e nome indexado da opção,
                  lido do formulário da aba, e traz os documentos gravados
                  com qualquer dos dois (medido com "medicamento":
                  ``"QUINTA TURMA"`` traz 576 documentos, contra 443 do
                  rótulo sozinho e 133 do nome indexado sozinho). Rótulo de
                  mais de uma opção, como ``"5ª Turma"`` nos acórdãos, levanta
                  ``ValueError``; texto que não casa com nenhuma opção vai
                  como está e só encontra o que o portal grava com essa
                  grafia. Não existe nas bases de monocráticas.
                * ``ementa`` (str): Texto pesquisado só na ementa. Não existe
                  nas bases de monocráticas.
                * ``indexacao`` (str): Texto pesquisado na indexação ("Objeto
                  do Processo" nas Turmas Recursais). Não existe nas bases de
                  monocráticas.
                * ``numero_classe`` (str): Número do processo dentro da
                  classe, o que vem depois da classe na coluna ``classe`` dos
                  acórdãos antigos (``"1708075"`` em
                  ``"Ap - APELAÇÃO CÍVEL - 1708075"``). Só na base
                  ``"acordaos"``.
                * ``sistema_interamericano`` (int | str): Caso da Corte IDH
                  do dropdown "Sistema Interamericano" do formulário, pelo ID
                  da opção ou por um trecho do nome (em 15/11/2026, ``1`` era
                  o caso Trabalhadores da Fazenda Brasil Verde e ``2``, o caso
                  Gomes Lund, "Guerrilha do Araguaia"; ``"Gomes Lund"`` acha o
                  ``2``). O nome é comparado sem acento, aspas e travessões
                  tipográficos, caixa ou espaços extras com as opções lidas
                  da aba e tem que corresponder a uma só; senão,
                  ``ValueError`` lista as opções. Texto só de dígitos vale
                  como ID. Só na base ``"acordaos"``.
                * ``legislacao`` (str): Texto pesquisado nas referências
                  legislativas dos documentos (ex.: ``"LEI-8080"``, ou
                  ``"LEI PELÉ FED LEI 9615 1998"``, o texto que o painel de
                  legislações do formulário escreve). Só na base
                  ``"acordaos"``.
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): Data de julgamento; nas monocráticas,
                  data da decisão. Aceita ``DD/MM/AAAA``, ``DD-MM-AAAA``,
                  ``AAAA-MM-DD``, ``AAAA/MM/DD``, ``date`` ou ``datetime``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): Data de publicação, nos mesmos
                  formatos. Não combina com ``data_julgamento_*``.
                * ``tamanho_pagina`` (int): 10 (default), 30 ou 50 documentos
                  por página.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando todos os erros são kwargs desconhecidos.
            ValidationError: Para os demais erros do schema (base ou
                ``tamanho_pagina`` fora do domínio, data inválida).
            ValueError: Datas de julgamento e de publicação juntas; filtro que o
                formulário da base não tem; nenhum critério;
                ``orgao_julgador`` que corresponde a mais de uma opção do
                formulário (a mensagem lista os nomes indexados que
                desfazem a ambiguidade); com ``paginas=None``, primeira
                página com documentos e total de resultados ilegível.
            BotChallengeBlockedError: A Akamai bloqueou o IP (HTTP 403
                ``Access Denied``).
            RuntimeError: O portal devolveu a página de sessão expirada, ou
                respondeu 200 com uma página que não é a lista de resultados
                (formulário de busca, manutenção), na primeira página ou nas
                seguintes; ou, da página 2 em diante, com o aviso de nenhum
                resultado quando a primeira página informou total maior que
                zero. Busca sem resultados não é erro: devolve DataFrame
                vazio.

        Returns:
            Uma linha por documento, com ``processo``,
                ``classe``, ``orgao_julgador``, ``relator``, ``relator_acordao``,
                ``data_julgamento``, ``data_publicacao``, ``meio_publicacao``
                (``DJEN``, ``Intimação via sistema``, ``e-DJF3 Judicial 1``...),
                ``ementa`` (nas monocráticas, o texto da decisão), ``base``,
                ``url_inteiro_teor`` (íntegra do acórdão no site do TRF3; vazio
                nas monocráticas) e ``inteiro_teor`` (texto completo). Em parte
                dos acórdãos antigos das Turmas Recursais, ``ementa`` vem nula
                porque o portal manda o bloco da ementa vazio; ``inteiro_teor``
                vem preenchido. Na medição, com "medicamento", foram nulas todas
                as ementas de 2013 e 2014 e parte das de 2011.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> trf3 = jus.scraper("trf3")
            >>> df = trf3.cjsg(
            ...     "medicamento", base="turmas_recursais", paginas=range(1, 3),
            ...     data_julgamento_inicio="2026-01-01", data_julgamento_fim="2026-06-30",
            ... )

        See Also:
            :class:`InputCJSGTRF3`: fonte dos filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Baixa as páginas da lista resumida da busca de jurisprudência do TRF3.

        Aceita os mesmos filtros de :meth:`cjsg`; veja lá a lista completa.

        Returns:
            HTML de cada página baixada, na ordem pedida.
        """
        inp = apply_input_pipeline_search(
            InputCJSGTRF3,
            "TRF3Scraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
            nullable_pesquisa=True,
        )
        validar_combinacoes(inp)
        with build_cjsg_session() as session:
            return cjsg_download_manager(
                inp,
                request_fn=self._request_with_retry,
                session=session,
                sleep_time=self.sleep_time,
            )

    def cjsg_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Converte as páginas de :meth:`cjsg_download` em DataFrame.

        Returns:
            Uma linha por documento; colunas descritas em :meth:`cjsg`.
        """
        return cjsg_parse_manager(resultados_brutos)
