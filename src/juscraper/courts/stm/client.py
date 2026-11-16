"""Raspador do Superior Tribunal Militar (STM)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import pandas as pd

from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import DATE_CANONICAL, apply_input_pipeline_search

from .download import cjsg_download_manager
from .parse import cjsg_parse_manager
from .schemas import InputCJSGSTM


class STMScraper(HTTPScraper):
    """Raspador do Superior Tribunal Militar.

    Usa a Consulta Judicial Unificada da Justiça Militar da União
    (``jurisprudencia.stm.jus.br``), na aba de jurisprudência, que reúne os
    acórdãos do STM. A aba de processos do mesmo portal, que cobre também as
    Auditorias das Circunscrições Judiciárias Militares, não está
    implementada.

    O portal fica atrás de um WAF que recusa pedidos conforme o IP de origem
    (em 16/11/2026, recusou todos os de um IP de datacenter fora do Brasil);
    nesse caso a busca levanta
    :class:`~juscraper.core.exceptions.BotChallengeBlockedError`.

    Args:
        sleep_time: Segundos entre duas páginas de resultados (default 1).
        download_path: Pasta de downloads. ``None`` usa um diretório temporário.
        verbose: Nível de detalhe do log.
        politica: Ajustes do perfil HTTP ``cjsg``, por campo de
            :class:`~juscraper.core.http.RequestPolicy`.
    """

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=60),
    }

    def __init__(
        self,
        *,
        sleep_time: float = 1.0,
        download_path: str | None = None,
        verbose: int = 0,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Cria o raspador; os argumentos estão na docstring da classe."""
        super().__init__(
            "STM", sleep_time=sleep_time, download_path=download_path, verbose=verbose, politica=politica
        )

    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Busca jurisprudência do STM.

        Args:
            pesquisa (str): Termo de busca. Aceita os operadores do portal:
                ``E`` (padrão entre palavras), ``OU``, ``NÃO``, aspas para
                expressão exata, ``*`` e ``?`` como curingas.
            paginas (int | list | range | None): Páginas 1-based, de 100
                documentos cada; ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGSTM`.
                Os cinco últimos são os da coluna "Filtrar por" do portal:
                opcionais (``None`` = sem filtro) e comparados com o valor
                exato que o portal exibe, em maiúsculas.

                * ``campo`` (str): Onde procurar o termo: ``"ementa"``
                  (default), ``"inteiro_teor"``, ``"numero"`` (número do
                  processo, completo ou parcial),
                  ``"referencia_legislativa"`` ou ``"tudo"`` (todos os
                  campos).
                * ``classe`` (str | None): Classe processual
                  (``"APELAÇÃO"``).
                * ``relator`` (str | None): Ministro relator
                  (``"CARLOS VUYK DE AQUINO"``).
                * ``relator_acordao`` (str | None): Ministro relator para o
                  acórdão.
                * ``revisor`` (str | None): Ministro revisor.
                * ``assunto`` (str | None): Assunto (``"PECULATO"``).
                * ``data_julgamento_inicio`` / ``data_julgamento_fim``
                  (str | date | None): Intervalo de data de julgamento, em
                  ``DD/MM/AAAA`` ou ``AAAA-MM-DD``.
                * ``data_publicacao_inicio`` / ``data_publicacao_fim``
                  (str | date | None): Intervalo de data de publicação.

                Com filtro de data, a busca vai pela pesquisa avançada do
                portal, a única que filtra por intervalo. Os operadores de
                ``pesquisa`` valem nela também: o raspador os traduz para a
                sintaxe da pesquisa avançada (``E``, ``OU`` e ``NÃO``, em
                qualquer caixa, viram ``AND``, ``OR`` e ``NOT``). Nela, o
                ``NÃO`` vem depois de um termo (``"furto NÃO roubo"``) e a
                mistura de ``E`` com ``OU`` pede parênteses
                (``"(furto roubo) OU peculato"``). Ela aceita
                ``pesquisa=""``, para trazer tudo o que está no intervalo, e
                não tem ``campo="tudo"``. Informado só um lado do intervalo,
                o outro é preenchido (01/01/1990 ou hoje), com
                ``UserWarning``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``
            * ``data_inicio`` / ``data_fim`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_julgamento_de`` / ``_ate`` -> ``data_julgamento_inicio`` / ``_fim``
            * ``data_publicacao_de`` / ``_ate`` -> ``data_publicacao_inicio`` / ``_fim``

        Raises:
            TypeError: Quando um kwarg desconhecido é passado.
            ValidationError: Quando um filtro tem valor inválido, como um
                ``campo`` fora das cinco opções.
            ValueError: Quando uma data é inválida ou o início vem depois do
                fim; quando há filtro de data e ``campo="tudo"`` com termo, ou
                ``pesquisa`` tem barra invertida, aspas ou parênteses sem par,
                operador sem termo, ``NÃO`` sem termo antes, ``E`` e ``OU``
                misturados sem parênteses, curinga em palavra com símbolo além de
                ponto e hífen ou, em ``campo="numero"``, algo além do número
                do processo; quando a página devolvida não traz o contador de
                documentos nem o aviso de busca vazia.
            BotChallengeBlockedError: Quando o WAF do portal recusa a
                requisição.

        Returns:
            Uma linha por documento, do julgamento mais recente para o mais
                antigo, com ``processo``, ``classe``, ``relator``,
                ``relator_acordao``, ``revisor``, ``assunto``,
                ``data_autuacao``, ``data_julgamento``, ``data_publicacao``,
                ``ementa``, ``url_inteiro_teor`` (endereço do inteiro teor) e
                ``id_documento``. Busca sem resultados devolve o DataFrame
                vazio com as mesmas colunas.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> stm = jus.scraper("stm")
            >>> df = stm.cjsg("deserção", paginas=1)
            >>> df = stm.cjsg("deserção", data_julgamento_inicio="01/03/2025", data_julgamento_fim="31/03/2025")

        See Also:
            :class:`InputCJSGSTM` — schema pydantic é a fonte da verdade dos
            filtros aceitos.
        """
        return self.cjsg_parse(self.cjsg_download(
            pesquisa=pesquisa,
            paginas=paginas,
            **kwargs,
        ))

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Baixa as páginas de resultados da busca de jurisprudência do STM.

        Aceita os mesmos filtros de :meth:`cjsg`; veja lá a lista completa.

        Returns:
            O HTML de cada página, na ordem pedida.
        """
        inp = apply_input_pipeline_search(
            InputCJSGSTM,
            "STMScraper.cjsg_download()",
            pesquisa=pesquisa,
            paginas=paginas,
            kwargs=kwargs,
            consume_pesquisa_aliases=True,
        )
        return cjsg_download_manager(
            inp.pesquisa,
            inp.paginas,
            request_fn=self._request_with_retry,
            sleep_time=self.sleep_time,
            campo=inp.campo,
            datas=inp.model_dump(include=set(DATE_CANONICAL)),
            classe=inp.classe,
            relator=inp.relator,
            relator_acordao=inp.relator_acordao,
            revisor=inp.revisor,
            assunto=inp.assunto,
        )

    def cjsg_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Extrai os documentos das páginas baixadas por :meth:`cjsg_download`.

        Returns:
            O DataFrame descrito em :meth:`cjsg`.
        """
        return cjsg_parse_manager(resultados_brutos)
