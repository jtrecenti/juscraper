"""Client publico do agregador ComunicaCNJ.

Wrapper sobre a API publica de Comunicacoes Processuais do CNJ
(``https://comunicaapi.pje.jus.br/api/v1/comunicacao``). O metodo
:meth:`ComunicaCNJScraper.listar_comunicacoes` aceita um termo de busca
obrigatorio (``pesquisa``) e filtros opcionais por intervalo de
disponibilizacao (``data_disponibilizacao_inicio``/``_fim``), pagina o
resultado e devolve um ``pandas.DataFrame``.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.http import HTTPScraper
from ...utils.cnj import clean_cnj
from ...utils.params import normalize_paginas, raise_on_extra_kwargs, to_iso_date, validate_intervalo_datas
from .download import BASE_URL, DEFAULT_HEADERS, build_listar_comunicacoes_params
from .parse import parse_count, parse_items
from .schemas import InputListarComunicacoesComunicaCNJ

logger = logging.getLogger(__name__)


def _exigir_pesquisa_ou_numero(pesquisa: str | None, numero_processo: str | None) -> None:
    """Levanta antes do schema e da rede quando falta o filtro principal.

    O schema aceita os dois vazios (``pesquisa`` tem o tipo canônico ``str``,
    com ``""`` como ausência), então a exigência de um dos dois mora aqui.
    """
    # Número sem dígitos iria como ``numeroProcesso=""``, uma consulta sem filtro.
    if not pesquisa and not (numero_processo and clean_cnj(numero_processo)):
        raise ValueError(
            "ComunicaCNJScraper.listar_comunicacoes(): informe pesquisa, numero_processo ou os dois."
        )


class ComunicaCNJScraper(HTTPScraper):
    """Scraper para a API publica de Comunicacoes Processuais do CNJ."""

    INPUT_LISTAR_COMUNICACOES = InputListarComunicacoesComunicaCNJ

    def __init__(
        self,
        verbose: int = 1,
        sleep_time: float = 0.5,
    ):
        super().__init__("ComunicaCNJ", verbose=verbose, sleep_time=sleep_time)
        logger.info("ComunicaCNJScraper initialized.")

    def _configure_session(self, session: requests.Session) -> None:
        # API publica do CNJ espera User-Agent firefox-like e os
        # Origin/Referer do frontend oficial em comunica.pje.jus.br.
        session.headers.update(DEFAULT_HEADERS)

    def listar_comunicacoes(
        self,
        pesquisa: str | None = None,
        paginas: int | list[int] | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Lista comunicacoes processuais publicadas pelos tribunais via PJe.

        Args:
            pesquisa: Termo livre buscado no texto da comunicacao
                (parametro ``texto`` da API). Opcional quando
                ``numero_processo`` e passado.
            paginas: Intervalo 1-based. Aceita ``int`` (``3`` ->
                ``range(1, 4)``), ``list``, ``range`` ou ``None``
                (default = todas as paginas).
            **kwargs: Filtros opcionais aceitos pelo schema
                :class:`InputListarComunicacoesComunicaCNJ`:

                * ``numero_processo`` (str): Numero CNJ, com ou sem
                  formatacao; vai a API como ``numeroProcesso``, so com os
                  digitos. Use este filtro para as comunicacoes de um
                  processo: o termo livre nao encontra o processo pelo
                  numero.
                * ``data_disponibilizacao_inicio`` (str): Inicio do
                  intervalo de ``dataDisponibilizacao``. Aceita ISO
                  ``YYYY-MM-DD`` ou formato brasileiro ``DD/MM/YYYY``
                  (convertido para ISO antes do schema).
                * ``data_disponibilizacao_fim`` (str): Fim do intervalo de
                  ``dataDisponibilizacao``. Mesmos formatos aceitos.
                * ``itens_por_pagina`` (int): Resultados por requisicao
                  (1-100, default 100).

        Returns:
            DataFrame com uma linha por comunicacao. As colunas refletem
            o JSON ``items`` da API (campos como ``numero_processo``,
            ``siglaTribunal``, ``texto``, ``link``, etc.).

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValueError: Quando nem ``pesquisa`` nem ``numero_processo`` sao
                informados.
            ValidationError: Quando um filtro tem formato invalido.
            ValueError: Quando o intervalo de datas e invalido (fim antes
                de inicio, formato divergente do backend).

        Exemplo:
            >>> import juscraper as jus
            >>> s = jus.scraper("comunica_cnj")
            >>> df = s.listar_comunicacoes(
            ...     pesquisa="resolucao",
            ...     data_disponibilizacao_inicio="2024-01-01",
            ...     data_disponibilizacao_fim="2024-01-31",
            ...     paginas=range(1, 4),
            ... )

        See also:
            :class:`InputListarComunicacoesComunicaCNJ` -- schema pydantic
            e a fonte da verdade dos filtros aceitos.
        """
        _exigir_pesquisa_ou_numero(pesquisa, kwargs.get("numero_processo"))
        paginas_norm = normalize_paginas(paginas)

        # Aceita ``DD/MM/YYYY`` na entrada por conveniencia, mas a API
        # espera ISO ``YYYY-MM-DD``. ``to_iso_date`` e idempotente para
        # strings ja em ISO.
        for nome in ("data_disponibilizacao_inicio", "data_disponibilizacao_fim"):
            if kwargs.get(nome) is not None:
                kwargs[nome] = to_iso_date(kwargs[nome])

        try:
            inp = InputListarComunicacoesComunicaCNJ(
                pesquisa=pesquisa or "",
                paginas=paginas_norm,
                **kwargs,
            )
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc,
                "ComunicaCNJScraper.listar_comunicacoes()",
                schema_cls=InputListarComunicacoesComunicaCNJ,
            )
            raise

        validate_intervalo_datas(
            inp.data_disponibilizacao_inicio,
            inp.data_disponibilizacao_fim,
            rotulo="data_disponibilizacao",
            max_dias=None,
            origem="O ComunicaCNJ",
            formato="%Y-%m-%d",
        )

        def _params_para_pagina(pagina: int) -> dict:
            return build_listar_comunicacoes_params(
                pesquisa=inp.pesquisa,
                numero_processo=inp.numero_processo,
                pagina=pagina,
                itens_por_pagina=inp.itens_por_pagina,
                data_disponibilizacao_inicio=inp.data_disponibilizacao_inicio,
                data_disponibilizacao_fim=inp.data_disponibilizacao_fim,
            )

        # Descobrir total de paginas a partir da pagina 1 quando o usuario
        # nao especificou ``paginas`` (ou para fechar o ``range``).
        primeira_resp = self._request_with_retry(
            "GET", BASE_URL, params=_params_para_pagina(1), timeout=30.0
        )
        total = parse_count(primeira_resp)
        total_paginas = max(1, (total + inp.itens_por_pagina - 1) // inp.itens_por_pagina)
        if self.verbose:
            logger.info("ComunicaCNJ: %d resultados em %d paginas.", total, total_paginas)

        if paginas_norm is None:
            paginas_iter: range | list = range(1, total_paginas + 1)
        elif isinstance(paginas_norm, range):
            paginas_iter = range(
                max(1, paginas_norm.start),
                min(paginas_norm.stop, total_paginas + 1),
            )
        else:
            paginas_iter = [p for p in paginas_norm if 1 <= p <= total_paginas]

        rows: list[dict] = []
        for pagina in tqdm(list(paginas_iter), desc="ComunicaCNJ", disable=not self.verbose):
            if pagina == 1:
                resp = primeira_resp
            else:
                if self.sleep_time:
                    time.sleep(self.sleep_time)
                resp = self._request_with_retry(
                    "GET", BASE_URL, params=_params_para_pagina(pagina), timeout=30.0
                )
            rows.extend(parse_items(resp))

        return pd.DataFrame(rows)
