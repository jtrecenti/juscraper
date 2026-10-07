"""Scraper for the Tribunal Regional Federal da 3ª Região (TRF3).

Wraps the PJe public-consultation system at ``pje1g.trf3.jus.br/pje/``. The
TRF3 deployment sits behind an Akamai bot manager (``ak_bmsc`` cookie) which
silently drops connections that don't carry a realistic browser header set;
the ``BROWSER_HEADERS`` applied by
:meth:`juscraper.courts._trf.base.TRFConsultaScraper._configure_session` are
tuned to pass that challenge. The form layout matches TRF1 (autocomplete
``classeJudicial`` + ``dataAutuacaoDecoration``), so only :data:`BASE_URL`
diverges.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

import pandas as pd

from ...core.http import RequestPolicy
from ...utils.params import apply_input_pipeline_search
from .._trf.base import TRFConsultaScraper
from .cjsg_download import DATA_TIPO, build_cjsg_payload, build_cjsg_session, cjsg_download_manager
from .cjsg_parse import cjsg_parse_manager
from .cjsg_schemas import InputCJSGTRF3, validar_combinacoes


class TRF3Scraper(TRFConsultaScraper):
    """TRF3 PJe consulta pública (1º grau)."""

    BASE_URL = "https://pje1g.trf3.jus.br/pje/"
    TRIBUNAL_NAME = "TRF3"

    #: Perfil HTTP da busca de jurisprudência. Parte das requisições ao portal
    #: fica pendurada atrás da Akamai sem responder; o timeout curto com nova
    #: tentativa recupera esses casos em segundos.
    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(
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
        **kwargs,
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
                * ``orgao_julgador`` (str): Órgão julgador como o portal indexa.
                  Nos acórdãos recentes do TRF3, ``"3ª Turma"``; nos antigos,
                  ``"TERCEIRA TURMA"``. Nas Turmas Recursais, o nome curto
                  (``"11ª TURMA RECURSAL DE SÃO PAULO"``). O valor da coluna
                  ``orgao_julgador`` do resultado nem sempre serve como
                  filtro: nas Turmas Recursais a coluna traz
                  ``"11ª Turma Recursal da Seção Judiciária de São Paulo"``,
                  que não encontra nada, enquanto
                  ``"11ª TURMA RECURSAL DE SÃO PAULO"`` encontra. "1a. seção"
                  vira "1A", como no formulário do portal, então
                  ``"QUINTA TURMA - 1A. SEÇÃO"`` busca
                  ``"QUINTA TURMA - 1A"``. Não existe nas bases de
                  monocráticas.
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
                base de monocráticas não tem; nenhum critério; com
                ``paginas=None``, total de resultados ilegível.
            BotChallengeBlockedError: A Akamai bloqueou o IP (HTTP 403
                ``Access Denied``).
            RuntimeError: O portal devolveu a página de sessão expirada.

        Returns:
            pd.DataFrame: Uma linha por documento, com ``processo``,
            ``classe``, ``orgao_julgador``, ``relator``, ``relator_acordao``,
            ``data_julgamento``, ``data_publicacao``, ``meio_publicacao``
            (``DJEN``, ``Intimação via sistema``, ``e-DJF3 Judicial 1``...),
            ``ementa`` (nas monocráticas, o texto da decisão), ``base``,
            ``url_inteiro_teor`` (íntegra do acórdão no site do TRF3; vazio
            nas monocráticas) e ``inteiro_teor`` (texto completo). Nos
            acórdãos antigos das Turmas Recursais (2010 a 2014), ``ementa``
            vem nula porque o portal manda o bloco da ementa vazio;
            ``inteiro_teor`` vem preenchido.

        Exemplo:
            >>> import juscraper as jus
            >>> trf3 = jus.scraper("trf3")
            >>> df = trf3.cjsg(
            ...     "medicamento", base="turmas_recursais", paginas=range(1, 3),
            ...     data_julgamento_inicio="2026-01-01", data_julgamento_fim="2026-06-30",
            ... )

        See also:
            :class:`InputCJSGTRF3`: fonte dos filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(pesquisa=pesquisa, paginas=paginas, **kwargs))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs,
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
        por_publicacao = bool(inp.data_publicacao_inicio or inp.data_publicacao_fim)
        payload = build_cjsg_payload(
            inp.pesquisa,
            base=inp.base,
            tamanho_pagina=inp.tamanho_pagina,
            numero_processo=inp.numero_processo or "",
            relator=inp.relator or "",
            classe=inp.classe or "",
            orgao_julgador=inp.orgao_julgador or "",
            ementa=inp.ementa or "",
            indexacao=inp.indexacao or "",
            data_inicial=(inp.data_publicacao_inicio if por_publicacao else inp.data_julgamento_inicio) or "",
            data_final=(inp.data_publicacao_fim if por_publicacao else inp.data_julgamento_fim) or "",
            data_tipo=DATA_TIPO["publicacao" if por_publicacao else "julgamento"],
        )
        return cjsg_download_manager(
            payload,
            base=inp.base,
            paginas=inp.paginas,
            tamanho_pagina=inp.tamanho_pagina,
            request_fn=self._request_with_retry,
            session=build_cjsg_session(),
            sleep_time=self.sleep_time,
            perfil="cjsg",
        )

    def cjsg_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Converte as páginas de :meth:`cjsg_download` em DataFrame.

        Returns:
            pd.DataFrame: Uma linha por documento; colunas descritas em :meth:`cjsg`.
        """
        return cjsg_parse_manager(resultados_brutos)
