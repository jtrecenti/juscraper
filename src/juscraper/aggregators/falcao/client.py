"""Client publico do agregador Falcao (Jurisprudencia Nacional da JT).

Wrapper sobre a busca publica do sistema "Jurisprudencia Nacional" da Justica
do Trabalho (``https://jurisprudencia.jt.jus.br``, backend interno ``falcao``,
mantido pelo CSJT). O endpoint ``/no-auth/pesquisa`` cobre TST e os 24 TRTs
sobre cinco colecoes de documentos (:data:`.schemas.COLECOES`).

O metodo :meth:`FalcaoScraper.cjsg` aceita um termo de busca obrigatorio
(``pesquisa``), a colecao alvo e filtros opcionais, pagina o resultado e
devolve um ``pandas.DataFrame``. O par :meth:`cjsg_download` /
:meth:`cjsg_parse` separa a coleta (JSON bruto em disco) do parsing.
"""
from __future__ import annotations

import json
import logging
import math
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.http import HTTPScraper
from ...utils.params import coerce_brazilian_date, normalize_paginas, raise_on_extra_kwargs, validate_intervalo_datas
from .download import DEFAULT_HEADERS, SEARCH_URL, build_pesquisa_params, gerar_session_id
from .parse import parse_documentos, parse_total
from .schemas import COLECOES, InputCJSGFalcao

logger = logging.getLogger(__name__)

# Teto imposto pelo backend Elasticsearch: ``page*size`` acima de 10000 e
# rejeitado, mesmo que ``quantidadeTotal`` reporte 10000 fixo.
_MAX_RESULTADOS = 10000


class FalcaoScraper(HTTPScraper):
    """Scraper para a Jurisprudencia Nacional da Justica do Trabalho (CSJT)."""

    INPUT_CJSG = InputCJSGFalcao
    COLECOES = COLECOES

    def __init__(
        self,
        verbose: int = 1,
        download_path: str | None = None,
        sleep_time: float = 1.0,
    ):
        super().__init__(
            "Falcao",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
        )
        # Um sessionId por instancia, reusado em todas as paginas — espelha o
        # cookie de 30 dias do frontend oficial.
        self.session_id = gerar_session_id()
        logger.info("FalcaoScraper initialized (sessionId=%s).", self.session_id)

    def _configure_session(self, session: requests.Session) -> None:
        # O WAF do site checa Origin/Referer; o backend exige Accept JSON.
        session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------ #
    # cjsg (jurisprudencia)
    # ------------------------------------------------------------------ #
    def cjsg(
        self,
        pesquisa: str | None = None,
        paginas: int | list[int] | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Consulta a Jurisprudencia Nacional da Justica do Trabalho.

        Baixa as paginas para um diretorio temporario e devolve o resultado
        parseado. Para inspecionar o JSON bruto, use :meth:`cjsg_download` +
        :meth:`cjsg_parse`.

        Args:
            pesquisa (str): Termo de busca livre (parametro ``texto``).
                Obrigatorio.
            paginas (int | list | range | None): Paginas 1-based; ``None``
                baixa todas as disponiveis (respeitando o teto de 10000
                resultados do backend). Default ``None``.
            **kwargs: Filtros aceitos pelo schema :class:`InputCJSGFalcao`.
                Listados abaixo (todos opcionais salvo indicacao):

                * ``colecao`` (str): Colecao alvo. Uma de
                  ``acordaos``, ``sentencas``, ``decisoesmonocraticas``,
                  ``precedentes``, ``recursorevista``. Default ``"acordaos"``.
                * ``tamanho_pagina`` (int): Documentos por pagina. So ``5`` ou
                  ``10`` (limite do backend para usuario nao autenticado).
                  Default ``10``.
                * ``tribunais`` (str | list[str]): Sigla(s) de tribunal
                  (``"TST"``, ``"TRT3"``, ...). Backend: ``tribunais``.
                * ``relator`` (str | list[str]): Nome(s) de relator. Backend:
                  ``nomeRelator``.
                * ``orgao_julgador`` (str | list[str]): Backend: ``orgaoJulgador``.
                * ``classe`` (str | list[str]): Classe(s) processual(is).
                  Backend: ``classeProcesso``.
                * ``fase_processual`` (str | list[str]): Backend: ``faseProcessual``.
                * ``prioridade`` (str | list[str]): Backend: ``prioridade``.
                * ``tem_ementa`` (bool): Restringe a documentos com/sem ementa.
                * ``somente_ementa`` (bool): Busca ``texto`` so nas ementas.
                * ``ordenacao`` (str): ``mais_relevante`` (default do backend),
                  ``mais_recente`` ou ``menos_recente``.
                * ``data_juntada_inicio`` / ``data_juntada_fim`` (str):
                  Intervalo de data de juntada. Aceita ``DD/MM/AAAA``,
                  ``AAAA-MM-DD`` ou ``date``; convertido para ISO antes do
                  backend (``dataInicio`` / ``dataFim``).

        Returns:
            pd.DataFrame: Uma linha por documento. Colunas canonicas
            garantidas: ``processo``, ``colecao``, ``tribunal`` e (quando a
            colecao os expoe) ``relator``, ``classe``, ``ementa``,
            ``data_julgamento``, ``data_juntada``. Campos brutos da colecao
            sao preservados.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ValidationError: Quando ``pesquisa`` falta ou um filtro tem valor
                invalido (``colecao``/``tamanho_pagina``/``ordenacao`` fora do
                dominio).
            ValueError: Quando o intervalo de datas e invalido.

        Exemplo:
            >>> import juscraper as jus
            >>> falcao = jus.scraper("falcao")
            >>> df = falcao.cjsg("dano moral", paginas=range(1, 3),
            ...                  tribunais=["TST", "TRT3"])

        See also:
            :class:`InputCJSGFalcao` -- schema pydantic e a fonte da verdade
            dos filtros aceitos.
        """
        with tempfile.TemporaryDirectory(prefix="falcao_cjsg_") as tmp:
            diretorio = self.cjsg_download(
                pesquisa=pesquisa, paginas=paginas, diretorio=tmp, **kwargs
            )
            return self.cjsg_parse(diretorio)

    def cjsg_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list[int] | range | None = None,
        diretorio: str | None = None,
        **kwargs,
    ) -> str:
        """Baixa as paginas cruas (JSON) da busca para um diretorio.

        Mesma validacao e filtros de :meth:`cjsg` (veja la a lista completa de
        ``**kwargs``). Cada pagina vira um arquivo
        ``{colecao}_{pagina:04d}.json`` dentro de um subdiretorio da busca.

        Args:
            pesquisa (str): Termo de busca. Obrigatorio.
            paginas (int | list | range | None): Paginas 1-based; ``None`` =
                todas. Default ``None``.
            diretorio (str | None): Sobrescreve ``download_path`` para esta
                chamada. Default ``None`` (usa ``download_path`` ou o diretorio
                atual).

        Returns:
            str: Caminho do subdiretorio com os arquivos JSON baixados.

        See also:
            :meth:`cjsg` -- lista completa de filtros aceitos.
        """
        paginas_norm = normalize_paginas(paginas)

        inp = self._validar_input(pesquisa, paginas_norm, kwargs)

        validate_intervalo_datas(
            inp.data_juntada_inicio,
            inp.data_juntada_fim,
            rotulo="data_juntada",
            max_dias=None,
            origem="O Falcao",
            formato="%Y-%m-%d",
        )

        def _params(pagina: int) -> dict:
            return build_pesquisa_params(
                pesquisa=inp.pesquisa,
                colecao=inp.colecao,
                session_id=self.session_id,
                pagina=pagina,
                tamanho_pagina=inp.tamanho_pagina,
                tribunais=inp.tribunais,
                relator=inp.relator,
                orgao_julgador=inp.orgao_julgador,
                classe=inp.classe,
                fase_processual=inp.fase_processual,
                prioridade=inp.prioridade,
                tem_ementa=inp.tem_ementa,
                somente_ementa=inp.somente_ementa,
                ordenacao=inp.ordenacao,
                data_juntada_inicio=inp.data_juntada_inicio,
                data_juntada_fim=inp.data_juntada_fim,
            )

        destino = self._preparar_destino(diretorio, inp.colecao)

        # Pagina 1 sempre e baixada — serve para descobrir o total.
        primeira = self._request_with_retry(
            "GET", SEARCH_URL, params=_params(1), timeout=30.0, expect_json=True
        )
        primeiro_json = primeira.json()
        total = parse_total(primeiro_json)
        total_paginas = self._total_paginas(total, inp.tamanho_pagina)
        if self.verbose:
            logger.info(
                "Falcao/%s: %d resultados (teto %d) em %d paginas de %d.",
                inp.colecao, total, _MAX_RESULTADOS, total_paginas,
                inp.tamanho_pagina,
            )

        paginas_iter = self._resolver_paginas(paginas_norm, total_paginas)

        for pagina in tqdm(
            list(paginas_iter), desc=f"Falcao/{inp.colecao}", disable=not self.verbose
        ):
            if pagina == 1:
                conteudo = primeiro_json
            else:
                if self.sleep_time:
                    time.sleep(self.sleep_time)
                resp = self._request_with_retry(
                    "GET", SEARCH_URL, params=_params(pagina),
                    timeout=30.0, expect_json=True,
                )
                conteudo = resp.json()
            arquivo = destino / f"{inp.colecao}_{pagina:04d}.json"
            arquivo.write_text(
                json.dumps(conteudo, ensure_ascii=False), encoding="utf-8"
            )

        return str(destino)

    def cjsg_parse(self, diretorio: str | Path) -> pd.DataFrame:
        """Le os arquivos JSON baixados por :meth:`cjsg_download`.

        A colecao de cada arquivo e inferida do prefixo do nome
        (``{colecao}_{pagina}.json``), o que permite parsear diretorios com
        varias colecoes misturadas.

        Args:
            diretorio (str | Path): Pasta com os arquivos JSON.

        Returns:
            pd.DataFrame: Resultados concatenados (veja :meth:`cjsg` para as
            colunas canonicas).
        """
        pasta = Path(diretorio)
        arquivos = sorted(pasta.glob("*.json"))
        rows: list[dict] = []
        for arquivo in arquivos:
            colecao = arquivo.stem.rsplit("_", 1)[0]
            data = json.loads(arquivo.read_text(encoding="utf-8"))
            rows.extend(parse_documentos(data, colecao))
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _validar_input(
        self, pesquisa: str | None, paginas_norm, kwargs: dict
    ) -> InputCJSGFalcao:
        """Coage datas, instancia o schema e traduz kwargs desconhecidos."""
        for nome in ("data_juntada_inicio", "data_juntada_fim"):
            if kwargs.get(nome) is not None:
                kwargs[nome] = coerce_brazilian_date(kwargs[nome], "%Y-%m-%d")
        try:
            return InputCJSGFalcao(pesquisa=pesquisa, paginas=paginas_norm, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(
                exc,
                "FalcaoScraper.cjsg()",
                schema_cls=InputCJSGFalcao,
            )
            raise

    def _preparar_destino(self, diretorio: str | None, colecao: str) -> Path:
        base = diretorio if diretorio is not None else (self.download_path or ".")
        destino = Path(base) / f"falcao_cjsg_{colecao}"
        destino.mkdir(parents=True, exist_ok=True)
        return destino

    @staticmethod
    def _total_paginas(total: int, tamanho_pagina: int) -> int:
        alcancavel = min(total, _MAX_RESULTADOS)
        return max(1, math.ceil(alcancavel / tamanho_pagina))

    @staticmethod
    def _resolver_paginas(paginas_norm, total_paginas: int):
        if paginas_norm is None:
            return range(1, total_paginas + 1)
        if isinstance(paginas_norm, range):
            return range(
                max(1, paginas_norm.start),
                min(paginas_norm.stop, total_paginas + 1),
            )
        return [p for p in paginas_norm if 1 <= p <= total_paginas]
