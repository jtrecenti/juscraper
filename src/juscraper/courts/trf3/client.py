"""Scraper for the Tribunal Regional Federal da 3ª Região (TRF3).

Covers two separate systems:

* ``cpopg`` wraps the PJe public-consultation system at
  ``pje1g.trf3.jus.br/pje/``. The TRF3 deployment sits behind an Akamai bot
  manager (``ak_bmsc`` cookie) which silently drops connections that don't
  carry a realistic browser header set; the ``BROWSER_HEADERS`` applied by
  :meth:`juscraper.courts._trf.base.TRFConsultaScraper._configure_session` are
  tuned to pass that challenge. The form layout matches TRF1 (autocomplete
  ``classeJudicial`` + ``dataAutuacaoDecoration``), so only :data:`BASE_URL`
  diverges.
* ``cjsg`` searches the case-law portal at ``web.trf3.jus.br/jurisprudencia``,
  an ASP.NET application unrelated to PJe, also behind Akamai. It does not use
  the PJe session: each search opens its own ``requests.Session`` with its own
  headers. What it takes from the scraper is the retry machinery of
  ``HTTPScraper``, the ``sleep_time`` given to the constructor and the HTTP
  profile ``perfis_http["cjsg"]`` (timeout and number of attempts). The code
  lives in :mod:`.cjsg_download`, :mod:`.cjsg_parse` and :mod:`.cjsg_schemas`.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from ...core.http import RequestPolicy
from ...utils.params import apply_input_pipeline_search
from .._trf.base import TRFConsultaScraper
from .cjsg_download import PERFIL_CJSG, build_cjsg_session, cjsg_download_manager
from .cjsg_parse import cjsg_parse_manager
from .cjsg_schemas import InputCJSGTRF3, validar_combinacoes


class TRF3Scraper(TRFConsultaScraper):
    """Raspador do TRF3: consulta pública do PJe e busca de jurisprudência.

    ``cpopg`` consulta processos de 1º grau no PJe (``pje1g.trf3.jus.br``),
    pela base :class:`TRFConsultaScraper`. ``cjsg`` pesquisa jurisprudência em
    ``web.trf3.jus.br/jurisprudencia``, um sistema separado, com sessão e
    perfil HTTP próprios (``perfis_http["cjsg"]``).
    """

    #: Endereço do PJe, usado pelo ``cpopg``. O do ``cjsg`` fica em
    #: ``cjsg_download.BASE_URL``.
    BASE_URL = "https://pje1g.trf3.jus.br/pje/"
    TRIBUNAL_NAME = "TRF3"

    #: Perfil HTTP da busca de jurisprudência. Parte das requisições ao portal
    #: fica pendurada atrás da Akamai sem responder; o timeout curto com nova
    #: tentativa recupera esses casos em segundos.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        PERFIL_CJSG: RequestPolicy(
            timeout=(10, 60),
            max_retries=4,
            retry_on_timeout=True,
            retry_on_connection_error=True,
        ),
    }

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
                * ``data_julgamento_inicio`` / ``data_julgamento_fim`` (str):
                  Data de julgamento; nas monocráticas, data da decisão.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim`` (str):
                  Data de publicação. Não combina com ``data_julgamento_*``.
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
            ValueError: Datas de julgamento e de publicação juntas; filtro que a
                base de monocráticas não tem; nenhum critério;
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
            pd.DataFrame: Uma linha por documento, com ``processo``,
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

        Exemplo:
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
            list[str]: HTML de cada página baixada, na ordem pedida.
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
        return cjsg_download_manager(
            inp,
            request_fn=self._request_with_retry,
            session=build_cjsg_session(),
            sleep_time=self.sleep_time,
        )

    def cjsg_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Converte as páginas de :meth:`cjsg_download` em DataFrame.

        Returns:
            pd.DataFrame: Uma linha por documento; colunas descritas em :meth:`cjsg`.
        """
        return cjsg_parse_manager(resultados_brutos)
