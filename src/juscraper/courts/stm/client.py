"""Raspador do Superior Tribunal Militar (STM)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import requests
from pydantic import ValidationError

from juscraper.core.download import gravar_arquivo
from juscraper.core.http import HTTPScraper, RequestPolicy
from juscraper.utils.params import DATE_CANONICAL, apply_input_pipeline_search, normalize_paginas, raise_on_extra_kwargs

from .download import cjsg_download_manager, conferir_bloqueio, processos_download_manager
from .inteiro_teor import InteiroTeorIndisponivelError, nome_do_arquivo, pdf_da_resposta
from .parse import cjsg_parse_manager, processos_parse_manager
from .schemas import InputCJSGSTM, InputListarProcessosSTM


class STMScraper(HTTPScraper):
    """Raspador do Superior Tribunal Militar.

    Usa a Consulta Judicial Unificada da Justiça Militar da União
    (``jurisprudencia.stm.jus.br``): a aba de jurisprudência, que reúne os
    acórdãos do STM (:meth:`cjsg`), e a aba de processos, que cobre também as
    Auditorias das Circunscrições Judiciárias Militares
    (:meth:`listar_processos`).

    O portal fica atrás de um WAF que recusa pedidos conforme o IP de origem
    (em 16/11/2026, recusou todos os de um IP de datacenter fora do Brasil);
    nesse caso a busca levanta
    :class:`~juscraper.core.exceptions.BotChallengeBlockedError`.

    Args:
        sleep_time: Segundos entre duas páginas de resultados (default 1).
        download_path: Pasta de downloads. ``None`` usa um diretório temporário.
        verbose: Nível de detalhe do log.
        politica: Ajustes dos perfis HTTP ``cjsg``, ``processos`` e ``inteiro_teor``, por campo de
            :class:`~juscraper.core.http.RequestPolicy`.
    """

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "cjsg": RequestPolicy(timeout=60),
        "processos": RequestPolicy(timeout=60),
        "inteiro_teor": RequestPolicy(timeout=120),
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

    def listar_processos(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> pd.DataFrame:
        """Lista processos do STM e das Auditorias da Justiça Militar da União.

        Usa a aba "Processos" do portal, com a capa de cada processo, as
        partes e os representantes. É preciso informar ``pesquisa`` ou ao
        menos um filtro.

        Args:
            pesquisa (str | None): Número do processo, completo ou parcial
                (``"7000374-06.2020.7.00.0000"``). ``None`` ou vazio lista
                os processos que os filtros selecionam.
            paginas (int | list | range | None): Páginas 1-based, de 100
                processos cada; ``None`` baixa todas. Default ``None``.
            **kwargs: Filtros aceitos pelo schema
                :class:`InputListarProcessosSTM`, os da coluna "Filtrar por"
                do portal: opcionais (``None`` = sem filtro) e comparados com
                o valor exato que o portal exibe, em maiúsculas.

                * ``cjm`` (str | None): Circunscrição Judiciária Militar
                  (``"11ª CIRCUNSCRIÇÃO JUDICIÁRIA MILITAR - DF"``).
                * ``orgao`` (str | None): Órgão (``"SUPERIOR TRIBUNAL
                  MILITAR"``, ``"AUDITORIA DA 5ª CJM"``).
                * ``conselho`` (str | None): Conselho de Justiça
                  (``"CONSELHO PERMANENTE DE JUSTIÇA - EXÉRCITO"``).
                * ``situacao`` (str | None): Situação do processo
                  (``"MOVIMENTO"``, ``"BAIXADO"``).
                * ``classe`` (str | None): Classe processual
                  (``"INQUÉRITO POLICIAL MILITAR"``).
                * ``assunto`` (str | None): Assunto (``"INCITAMENTO"``).

        Raises:
            TypeError: Quando um kwarg desconhecido é passado.
            ValidationError: Quando um filtro tem valor inválido.
            ValueError: Quando não há ``pesquisa`` nem filtro; quando a página
                devolvida não traz o contador de documentos nem o aviso de
                busca vazia.
            BotChallengeBlockedError: Quando o WAF do portal recusa a
                requisição.

        Returns:
            Uma linha por processo, da autuação mais recente para a mais
                antiga, com ``processo``, ``classe``, ``orgao``, ``conselho``,
                ``relator``, ``revisor``, ``juiz``, ``data_autuacao`` (com a
                hora), ``situacao``, ``assunto`` (os assuntos num texto só,
                numerados como no portal), ``partes`` (lista de dicionários
                com ``tipo``, ``nome`` e ``qualificacao``, o posto e a força
                que o portal mostra),
                ``representantes`` (lista de dicionários com ``tipo``,
                ``nome`` e ``partes``, os nomes de quem ele representa) e
                ``url_processo`` (endereço do processo no eproc). Busca sem
                resultados devolve o DataFrame vazio com as mesmas colunas.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> stm = jus.scraper("stm")
            >>> df = stm.listar_processos("7000374-06.2020.7.00.0000")
            >>> df = stm.listar_processos(assunto="INCITAMENTO", situacao="MOVIMENTO")

        See Also:
            :class:`InputListarProcessosSTM` — schema pydantic é a fonte da
            verdade dos filtros aceitos.
        """
        return self.listar_processos_parse(self.listar_processos_download(
            pesquisa=pesquisa,
            paginas=paginas,
            **kwargs,
        ))

    def listar_processos_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list | range | None = None,
        **kwargs: Any,
    ) -> list[str]:
        """Baixa as páginas de resultados da busca de processos do STM.

        Aceita os mesmos filtros de :meth:`listar_processos`; veja lá a lista completa.

        Returns:
            O HTML de cada página, na ordem pedida.
        """
        # Sem o pipeline das buscas de jurisprudência: ele consome os aliases
        # de ``pesquisa`` e de datas, que este método não tem.
        paginas_pedidas = normalize_paginas(paginas)
        try:
            inp = InputListarProcessosSTM(
                pesquisa="" if pesquisa is None else pesquisa, paginas=paginas_pedidas, **kwargs
            )
        except ValidationError as erro:
            raise_on_extra_kwargs(erro, "STMScraper.listar_processos_download()", schema_cls=InputListarProcessosSTM)
            raise
        termo = inp.pesquisa.strip()
        filtros = inp.model_dump(exclude={"pesquisa", "paginas"})
        if not termo and not any(filtros.values()):
            raise ValueError(
                "STM: listar_processos precisa de 'pesquisa' (número do processo) ou de ao menos um filtro "
                f"({', '.join(filtros)})."
            )
        return processos_download_manager(
            termo, paginas_pedidas, request_fn=self._request_with_retry, sleep_time=self.sleep_time, **filtros
        )

    def listar_processos_parse(self, resultados_brutos: list[str]) -> pd.DataFrame:
        """Extrai os processos das páginas baixadas por :meth:`listar_processos_download`.

        Returns:
            O DataFrame descrito em :meth:`listar_processos`.
        """
        return processos_parse_manager(resultados_brutos)

    def baixar_inteiro_teor(self, url_inteiro_teor: str, diretorio: str | None = None) -> str:
        """Baixa o PDF do inteiro teor de um acórdão do STM.

        Um pedido por acórdão, sem login e sem captcha. Devolve o PDF como o
        tribunal o publica; a extração de texto fica com quem usa a
        biblioteca.

        Args:
            url_inteiro_teor (str): Endereço do inteiro teor, como vem na
                coluna ``url_inteiro_teor`` do :meth:`cjsg`: o visualizador
                do eproc (``https://eproc2g.stm.jus.br/...&uuid=...``), nos
                acórdãos recentes, ou o PDF em
                ``https://www2.stm.jus.br/pesquisa/acordao/...``, nos antigos.
            diretorio (str | None): Pasta de destino. Default
                :attr:`download_path`. O PDF vai para
                ``<diretorio>/inteiro_teor/<nome>.pdf``, em que ``<nome>`` é
                o ``uuid`` do endereço do eproc ou, em ``www2``, o ano, a
                classe e o nome do arquivo (``2015_50_10022722``).

        Raises:
            ValueError: Endereço fora desses dois formatos (a célula vazia de
                um acórdão sem inteiro teor, por exemplo), antes de qualquer
                pedido.
            BotChallengeBlockedError: Quando o WAF do portal recusa a
                requisição.
            InteiroTeorIndisponivelError: O portal respondeu sem PDF ou com
                erro HTTP que não se resolve pedindo de novo (o 404 de um
                arquivo que saiu do ar, por exemplo); nada é gravado. Fica em
                ``juscraper.courts.stm.inteiro_teor``.
            RetryExhaustedError: O portal seguiu respondendo com status
                passageiro (429, 503) depois de todas as tentativas; vale
                pedir de novo mais tarde.

        Returns:
            Caminho do PDF gravado.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> stm = jus.scraper("stm")
            >>> df = stm.cjsg("deserção", paginas=1)
            >>> caminho = stm.baixar_inteiro_teor(df["url_inteiro_teor"].dropna().iloc[0])
        """
        nome = nome_do_arquivo(url_inteiro_teor)
        url = url_inteiro_teor.strip()
        try:
            resposta = self._request_with_retry("GET", url, perfil="inteiro_teor", on_response=conferir_bloqueio)
        except requests.HTTPError as erro:
            raise InteiroTeorIndisponivelError(url, f"o STM respondeu com erro ({erro}); nada foi gravado.") from erro
        destino = Path(diretorio or self.download_path) / "inteiro_teor" / nome
        return str(gravar_arquivo(pdf_da_resposta(resposta, url), destino))
