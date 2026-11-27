"""Client publico do agregador Falcao (Jurisprudencia Nacional da JT).

Wrapper sobre a busca publica do sistema "Jurisprudencia Nacional" da Justica
do Trabalho (``https://jurisprudencia.jt.jus.br``, backend interno ``falcao``,
mantido pelo CSJT). O endpoint ``/no-auth/pesquisa`` cobre TST e os 24 TRTs
sobre cinco colecoes de documentos (:data:`.schemas.COLECOES`).

O metodo :meth:`FalcaoScraper.listar_decisoes` aceita um termo de busca obrigatorio
(``pesquisa``), a colecao alvo e filtros opcionais, pagina o resultado e
devolve um ``pandas.DataFrame``. O par :meth:`listar_decisoes_download` /
:meth:`listar_decisoes_parse` separa a coleta (JSON bruto em disco) do parsing.
"""
from __future__ import annotations

import json
import logging
import math
import shutil
import tempfile
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

import pandas as pd
import requests
from pydantic import ValidationError
from tqdm.auto import tqdm

from ...core.avisos import avisar
from ...core.base import mensagem_de_kwargs_inesperados
from ...core.http import HTTPScraper, RequestPolicy
from ...utils.params import (
    coerce_brazilian_date,
    normalize_paginas,
    normalize_pesquisa,
    raise_on_extra_kwargs,
    validate_intervalo_datas,
)
from . import _checkpoint
from .download import (
    DATA_INICIO_PISO,
    DEFAULT_HEADERS,
    SEARCH_URL,
    build_pesquisa_params,
    gerar_session_id,
    identidade_da_busca,
    verificar_resposta,
)
from .parse import parse_documentos, parse_total
from .schemas import COLECOES, InputListarDecisoesFalcao

logger = logging.getLogger(__name__)

# Teto imposto pelo backend Elasticsearch: ``page*size`` acima de 10000 e
# rejeitado, e ``quantidadeTotal`` tambem para em 10000, entao o total
# reportado nao distingue "exatamente 10000" de "10000 ou mais".
_MAX_RESULTADOS = 10000

_FORMATO_BACKEND = "%Y-%m-%d"


class FalcaoScraper(HTTPScraper):
    """Scraper para a Jurisprudencia Nacional da Justica do Trabalho (CSJT)."""

    INPUT_LISTAR_DECISOES = InputListarDecisoesFalcao
    COLECOES = COLECOES

    perfis_http: ClassVar[Mapping[str, RequestPolicy]] = {
        "listagem": RequestPolicy(timeout=30.0, expect_json=True),
    }

    def __init__(
        self,
        verbose: int = 1,
        download_path: str | None = None,
        sleep_time: float = 1.0,
        *,
        politica: Mapping[str, Mapping[str, Any]] | None = None,
    ):
        super().__init__(
            "Falcao",
            verbose=verbose,
            download_path=download_path,
            sleep_time=sleep_time,
            politica=politica,
        )
        # Um sessionId por instancia, reusado em todas as paginas — espelha o
        # cookie de 30 dias do frontend oficial.
        self.session_id = gerar_session_id()
        logger.info("FalcaoScraper initialized (sessionId=%s).", self.session_id)

    def _configure_session(self, session: requests.Session) -> None:
        # O WAF do site checa Origin/Referer; o backend exige Accept JSON.
        session.headers.update(DEFAULT_HEADERS)

    # ------------------------------------------------------------------ #
    # listar_decisoes (jurisprudencia)
    # ------------------------------------------------------------------ #
    def listar_decisoes(
        self,
        pesquisa: str | None = None,
        paginas: int | list[int] | range | None = None,
        **kwargs,
    ) -> pd.DataFrame:
        """Consulta a Jurisprudencia Nacional da Justica do Trabalho.

        Baixa as páginas para um diretório próprio no temporário do sistema
        (``tempfile.gettempdir()``), sem usar ``download_path``, e o remove
        após devolver o resultado parseado.
        Se a coleta ou o parsing falhar, preserva as páginas recebidas nesse
        diretório e informa o caminho em uma nota da exceção. Recupere
        esse resultado parcial com :meth:`listar_decisoes_parse`. Para guardar
        também coletas completas, use :meth:`listar_decisoes_download`.

        Com ``checkpoint_dir``, as páginas vão para esse diretório, que não é
        removido, e ``resume=True`` continua uma coleta interrompida (pela
        cota diária do backend, por exemplo) requisitando só as páginas que
        faltam. O DataFrame traz todas as páginas presentes no checkpoint.

        A ordem padrão (``mais_relevante``) varia entre chamadas da mesma
        busca (medido em 16/11/2026: três versões da mesma página em três
        minutos), e páginas requisitadas em momentos diferentes podem
        repetir ou omitir documentos: nessa ordem, a coleta de mais de uma
        página, ou com ``checkpoint_dir``, emite ``UserWarning``. Para
        várias páginas ou vários dias, use ``ordenacao="menos_recente"``
        com ``data_juntada_fim`` fechado no passado, combinação que devolveu
        a mesma página em três chamadas. ``mais_recente`` não foi medida;
        nela, cada documento novo desloca as páginas seguintes.

        Limites do checkpoint:

        * Entre sessões o índice pode mudar. Se o total da busca mudar, as
          páginas já gravadas são mantidas e um ``UserWarning`` avisa que
          elas podem repetir ou omitir documentos em relação às novas.
          Mudança que conserva o total (inclusive acima do teto de 10000)
          não é detectada: conferi-la exigiria requisitar de novo as
          páginas gravadas.
        * O checkpoint completo não é reaberto para documentos novos: vale
          o total registrado, e a retomada não gasta requisição. Para os
          documentos juntados depois, faça outra coleta, em outro
          diretório, com ``data_juntada_inicio``.
        * ``resume=True`` exige o checkpoint, como no STF: caminho errado
          falha em vez de começar do zero. Num script diário de chamada
          única, passe
          ``resume=(Path(checkpoint_dir) / "manifest.json").exists()``.
        * Não há trava de diretório: duas execuções simultâneas no mesmo
          checkpoint requisitam as mesmas páginas e gastam a cota em dobro.

        Args:
            pesquisa (str): Termo de busca livre (parametro ``texto``).
                Obrigatorio.
            paginas (int | list | range | None): Paginas 1-based; ``None``
                baixa todas as disponiveis, ate o teto de 10000 resultados
                do backend (acima dele, emite ``UserWarning``). Default
                ``None``. Páginas selecionadas além do teto são ignoradas
                sem requisição.
            **kwargs: Filtros aceitos pelo schema :class:`InputListarDecisoesFalcao`.
                Listados abaixo (todos opcionais salvo indicacao):

                * ``colecao`` (str): Colecao alvo. Uma de
                  ``acordaos``, ``sentencas``, ``decisoesmonocraticas``,
                  ``precedentes``, ``recursorevista``. Default ``"acordaos"``.
                  ``precedentes`` devolve enunciados (sumulas, OJs), nao
                  decisoes.
                * ``tamanho_pagina`` (int): Documentos por pagina. So ``5`` ou
                  ``10`` (limite do backend para usuario nao autenticado).
                  Default ``10``.
                * ``tribunais`` (str | list[str]): Sigla(s) de tribunal
                  (``"TST"``, ``"TRT3"``, ...). Backend: ``tribunais``.
                * ``relator`` (str | list[str]): Nome(s) de relator. Backend:
                  ``nomeRelator``.
                * ``orgao_julgador`` (str | list[str]): Backend: ``orgaoJulgador``.
                * ``classe`` (str | list[str]): Sigla(s) da classe processual
                  (``"ROT"``, ``"ATOrd"``), a mesma da coluna de saida
                  ``classe_sigla``. O nome por extenso devolve zero
                  resultados sem erro. Backend: ``classeProcesso``.
                * ``fase_processual`` (str | list[str]): Backend: ``faseProcessual``.
                * ``prioridade`` (str | list[str]): Backend: ``prioridade``.
                * ``tem_ementa`` (bool): Restringe a documentos com/sem ementa.
                * ``somente_ementa`` (bool): Busca ``texto`` so nas ementas.
                * ``ordenacao`` (str): ``mais_relevante`` (default do backend),
                  ``mais_recente`` ou ``menos_recente``.
                * ``data_juntada_inicio`` / ``data_juntada_fim`` (str):
                  Intervalo de data de juntada. Aceita ``DD/MM/AAAA``,
                  ``AAAA-MM-DD`` ou ``date``; convertido para ISO antes do
                  backend (``dataInicio`` / ``dataFim``). Cada limite pode
                  ser usado sozinho; só com o limite superior, a busca
                  envia ``dataInicio=1900-01-01``, porque o backend
                  rejeita ``dataFim`` sozinho; limite superior anterior a
                  essa data levanta ``ValueError``.
                * ``checkpoint_dir`` (str | Path): Diretório de páginas e
                  manifesto da coleta retomável. Diretório ocupado exige
                  ``resume=True``; nunca é sobrescrito por coleta nova.
                * ``resume`` (bool): Retoma o checkpoint da mesma busca
                  (mesmo termo, coleção, filtros e ``tamanho_pagina``), sem
                  requisitar as páginas já gravadas. ``paginas`` pode mudar
                  entre sessões, e a ordem dos valores de um filtro em
                  lista não importa. Default ``False``.

        Aliases deprecados (popados com ``DeprecationWarning`` antes do pydantic):
            * ``query`` / ``termo`` -> ``pesquisa``

        Returns:
            Uma linha por documento. Colunas canonicas
                garantidas: ``processo``, ``colecao``, ``tribunal``, ``relator``,
                ``classe``, ``classe_sigla`` e, quando a colecao os expoe,
                ``ementa`` (texto sem HTML), ``data_julgamento`` e
                ``data_juntada``. Os demais campos brutos da colecao sao
                preservados, exceto os ``highlight*`` (ver
                :class:`OutputListarDecisoesFalcao`).

        Raises:
            TypeError: Quando um kwarg desconhecido e passado (inclusive
                ``diretorio``, que so :meth:`listar_decisoes_download` aceita).
            ValidationError: Quando ``pesquisa`` falta ou um filtro tem valor
                invalido (``colecao``/``tamanho_pagina``/``ordenacao`` fora do
                dominio).
            ValueError: Quando uma data e invalida, o intervalo esta
                invertido ou o backend recusa a busca (403 com mensagem).
                Tambem quando ``checkpoint_dir`` esta ocupado sem
                ``resume=True``, ou ``resume=True`` nao encontra o checkpoint
                da mesma busca.
            BotChallengeBlockedError: Quando o WAF (CloudFront) bloqueia a
                requisicao.
            requests.HTTPError: Quando o backend bloqueia o IP por excesso
                de requisicoes (429 com espera de horas).
            BaseException: Falhas de coleta, parsing ou interrupção manual
                são propagadas com nota sobre as páginas preservadas, se houver.

        Examples: Exemplo
            >>> import juscraper as jus
            >>> falcao = jus.scraper("falcao")
            >>> df = falcao.listar_decisoes("dano moral", paginas=range(1, 3),
            ...                  tribunais=["TST", "TRT3"],
            ...                  ordenacao="menos_recente",
            ...                  data_juntada_fim="2024-12-31")

        See also:
            :class:`InputListarDecisoesFalcao` -- schema pydantic e a fonte da verdade
            dos filtros aceitos.
        """
        metodo = "FalcaoScraper.listar_decisoes()"
        if "diretorio" in kwargs:
            raise TypeError(
                mensagem_de_kwargs_inesperados(metodo, ["'diretorio'"])
                + ". Para gravar o JSON bruto num diretorio, use listar_decisoes_download()."
            )
        if kwargs.get("checkpoint_dir") is not None:
            return self.listar_decisoes_parse(self._baixar(pesquisa, paginas, None, kwargs, metodo))
        # Não usa download_path: listar_decisoes_parse lê a pasta recursivamente, e
        # uma sobra preservada ali entraria no parse dos downloads guardados.
        temporario = Path(tempfile.mkdtemp(prefix="falcao_"))
        try:
            diretorio = self._baixar(pesquisa, paginas, temporario, kwargs, metodo)
            resultado = self.listar_decisoes_parse(diretorio)
        except BaseException as erro:
            # Inclui interrupção manual: a cota já foi gasta nas páginas recebidas.
            if any(temporario.rglob("*.json")):
                erro.add_note(
                    f"Páginas recebidas preservadas em {temporario}. "
                    "Use listar_decisoes_parse nesse diretório para recuperar o resultado parcial."
                )
            else:
                shutil.rmtree(temporario)
            raise
        shutil.rmtree(temporario)
        return resultado

    def listar_decisoes_download(
        self,
        pesquisa: str | None = None,
        paginas: int | list[int] | range | None = None,
        diretorio: str | None = None,
        **kwargs,
    ) -> str:
        """Baixa as paginas cruas (JSON) da busca para um diretorio.

        Mesma validacao e filtros de :meth:`listar_decisoes` (veja la a lista completa de
        ``**kwargs``). Cada chamada cria um subdiretorio proprio
        ``falcao_{colecao}_<sufixo aleatorio>``, entao buscas diferentes
        no mesmo ``diretorio`` nunca se misturam. Cada pagina vira um arquivo
        ``{colecao}_{pagina:04d}.json``.

        Com ``checkpoint_dir``, os arquivos vão direto para esse diretório,
        junto de um ``manifest.json``, e ``resume=True`` continua a coleta
        interrompida sem requisitar as páginas já gravadas.

        Args:
            pesquisa (str): Termo de busca. Obrigatorio.
            paginas (int | list | range | None): Paginas 1-based; ``None`` =
                todas. Default ``None``.
            diretorio (str | None): Sobrescreve ``download_path`` para esta
                chamada. Default ``None`` (usa o ``download_path`` do scraper,
                que sem configuracao e um diretorio temporario criado no
                primeiro uso). Cria a pasta e seus pais quando não existem.
                Não combina com ``checkpoint_dir``.

        Returns:
            Caminho do subdiretorio com os arquivos JSON baixados; com
                ``checkpoint_dir``, o próprio diretório do checkpoint.

        Raises:
            ValueError: Quando ``diretorio`` e ``checkpoint_dir`` vêm juntos.

        Avisos:
            ``UserWarning``: na ordem padrão (``mais_relevante``), que
            varia entre chamadas, ao coletar mais de uma página ou com
            ``checkpoint_dir``; veja :meth:`listar_decisoes`.

        See also:
            :meth:`listar_decisoes` -- lista completa de filtros aceitos.
        """
        base: str | None = diretorio
        if kwargs.get("checkpoint_dir") is not None:
            if diretorio is not None:
                raise ValueError("Use checkpoint_dir ou diretorio, não os dois: o checkpoint já define onde gravar.")
        elif diretorio is None:
            base = self.download_path
        return self._baixar(pesquisa, paginas, base, kwargs, "FalcaoScraper.listar_decisoes_download()")

    def listar_decisoes_parse(self, diretorio: str | Path) -> pd.DataFrame:
        """Le os arquivos JSON baixados por :meth:`listar_decisoes_download`.

        Percorre ``diretorio`` recursivamente, entao aceita tanto o caminho
        devolvido por :meth:`listar_decisoes_download` quanto a pasta-mae que junta
        varias buscas. A colecao de cada arquivo e inferida do prefixo do
        nome (``{colecao}_{pagina}.json``). O ``manifest.json`` de um
        checkpoint é ignorado.

        Args:
            diretorio (str | Path): Pasta com os arquivos JSON.

        Returns:
            Resultados concatenados (veja :meth:`listar_decisoes` para as
                colunas canonicas).
        """
        pasta = Path(diretorio)
        arquivos = sorted(a for a in pasta.rglob("*.json") if a.name != _checkpoint.MANIFESTO)
        rows: list[dict] = []
        for arquivo in arquivos:
            colecao = arquivo.stem.rsplit("_", 1)[0]
            data = json.loads(arquivo.read_text(encoding="utf-8"))
            rows.extend(parse_documentos(data, colecao))
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _baixar(self, pesquisa, paginas, base, kwargs: dict, metodo: str) -> str:
        """Valida a entrada, pagina a busca e grava cada pagina em ``base`` ou no checkpoint."""
        inp = self._validar_input(pesquisa, normalize_paginas(paginas), kwargs, metodo)
        if inp.checkpoint_dir is None:
            if inp.resume:
                raise ValueError("resume=True exige checkpoint_dir.")
            Path(base).mkdir(parents=True, exist_ok=True)
            destino = Path(tempfile.mkdtemp(prefix=f"falcao_{inp.colecao}_", dir=base))
            self._coletar(inp, destino)
            return str(destino)

        destino = Path(inp.checkpoint_dir)
        identidade = identidade_da_busca(self._params(inp, 1))
        checkpoint = _checkpoint.Checkpoint(destino, identidade, resume=inp.resume)
        self._avisar_ordem_instavel(inp)
        try:
            self._coletar(inp, destino, checkpoint)
        except BaseException as erro:
            # Inclui interrupção manual: a cota já foi gasta nas páginas recebidas.
            erro.add_note(
                f"Checkpoint da coleta em {destino}. "
                "Repita a chamada com resume=True para requisitar só as páginas que faltam."
            )
            raise
        return str(destino)

    def _coletar(
        self,
        inp: InputListarDecisoesFalcao,
        destino: Path,
        checkpoint: _checkpoint.Checkpoint | None = None,
    ) -> None:
        """Requisita as páginas pedidas que faltam em ``destino``.

        Sem ``checkpoint``, ``destino`` está vazio e nada é pulado.
        """
        gravadas = checkpoint.gravadas if checkpoint is not None else set()
        total_anterior = checkpoint.total if checkpoint is not None else None
        # A primeira pagina pendente serve tambem para ler o total; com
        # ``paginas`` que nao inclui a 1, isso poupa uma requisicao.
        primeira = self._primeira_pendente(inp, gravadas, total_anterior)
        if primeira is None:
            if total_anterior is not None:
                self._avisar_teto(inp, total_anterior)
            return
        primeiro_json = self._buscar_pagina(inp, primeira)
        # O total ou um aviso convertido em erro não pode apagar a resposta recebida.
        arquivo_inicial = destino / f"{inp.colecao}_{primeira:04d}.json"
        _checkpoint.gravar_json(arquivo_inicial, primeiro_json)
        total = parse_total(primeiro_json)
        if checkpoint is not None:
            checkpoint.observar(total)
        total_paginas = self._total_paginas(total, inp.tamanho_pagina)
        if self.verbose:
            logger.info(
                "Falcao/%s: %d resultados (teto %d) em %d paginas de %d.",
                inp.colecao, total, _MAX_RESULTADOS, total_paginas,
                inp.tamanho_pagina,
            )
        self._avisar_teto(inp, total)

        pendentes = [p for p in self._resolver_paginas(inp.paginas_normalizadas, total_paginas) if p not in gravadas]
        if primeira not in pendentes:
            arquivo_inicial.unlink()
        self._avisar_ordem_entre_paginas(inp, pendentes, checkpoint)
        for pagina in tqdm(pendentes, desc=f"Falcao/{inp.colecao}", disable=not self.verbose):
            if pagina == primeira:
                continue
            if self.sleep_time:
                time.sleep(self.sleep_time)
            conteudo = self._buscar_pagina(inp, pagina)
            _checkpoint.gravar_json(destino / f"{inp.colecao}_{pagina:04d}.json", conteudo)

    def _primeira_pendente(
        self, inp: InputListarDecisoesFalcao, gravadas: set[int], total_anterior: int | None,
    ) -> int | None:
        """Primeira página a requisitar, ou ``None`` se nenhuma das pedidas falta.

        O teto é conhecido antes da consulta: nenhuma página fora dele pode
        servir de primeira requisição, pois o backend a rejeita. Na retomada,
        vale o total da sessão anterior: página além dele não gasta a cota, e
        o checkpoint completo não requisita nada.
        """
        conhecido = _MAX_RESULTADOS if total_anterior is None else total_anterior
        total_paginas = self._total_paginas(conhecido, inp.tamanho_pagina)
        candidatas = self._resolver_paginas(inp.paginas_normalizadas, total_paginas)
        return next((p for p in candidatas if p not in gravadas), None)

    def _params(self, inp: InputListarDecisoesFalcao, pagina: int) -> dict:
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

    def _buscar_pagina(self, inp: InputListarDecisoesFalcao, pagina: int) -> dict:
        resp = self._request_with_retry(
            "GET", SEARCH_URL, params=self._params(inp, pagina), perfil="listagem", on_response=verificar_resposta,
        )
        dados: dict = resp.json()
        return dados

    @staticmethod
    def _validar_input(pesquisa: str | None, paginas_norm, kwargs: dict, metodo: str) -> InputListarDecisoesFalcao:
        """Resolve aliases, coage e valida datas e instancia o schema."""
        kwargs = dict(kwargs)
        aliases = {nome: kwargs.pop(nome) for nome in ("query", "termo") if nome in kwargs}
        if aliases:
            pesquisa = normalize_pesquisa(pesquisa, **aliases)
        for nome in ("data_juntada_inicio", "data_juntada_fim"):
            if kwargs.get(nome) is not None:
                kwargs[nome] = coerce_brazilian_date(kwargs[nome], _FORMATO_BACKEND)
                _validar_data(kwargs[nome], nome)
        try:
            # ``model_validate`` porque ``pesquisa`` chega como ``str | None``:
            # quem recusa ``None`` (sem termo nem alias) e o proprio schema.
            inp: InputListarDecisoesFalcao = InputListarDecisoesFalcao.model_validate(
                {"pesquisa": pesquisa, "paginas": paginas_norm, **kwargs},
            )
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, metodo, schema_cls=InputListarDecisoesFalcao)
            raise
        validate_intervalo_datas(
            inp.data_juntada_inicio,
            inp.data_juntada_fim,
            rotulo="data_juntada",
            max_dias=None,
            origem="O Falcao",
            formato=_FORMATO_BACKEND,
        )
        # Só com o fim, a busca envia o piso como ``dataInicio``, e o intervalo sairia invertido.
        # As duas datas já estão validadas em ISO, que ordena como texto.
        fim = inp.data_juntada_fim
        if inp.data_juntada_inicio is None and fim is not None and fim < DATA_INICIO_PISO:
            raise ValueError(
                f"'data_juntada_fim' ({fim}) é anterior a {DATA_INICIO_PISO}, "
                "o início que a busca envia quando só o limite superior é informado."
            )
        return inp

    def _avisar_ordem_entre_paginas(
        self, inp: InputListarDecisoesFalcao, pendentes: list[int], checkpoint: _checkpoint.Checkpoint | None,
    ) -> None:
        """Sem checkpoint, avisa da ordem instável só na coleta de mais de uma página.

        Com checkpoint, ``_baixar`` já avisou antes de requisitar, pois as páginas se
        somam entre sessões. Em lista, ``paginas`` pode repetir a mesma página.
        """
        if checkpoint is None and len(set(pendentes)) > 1:
            self._avisar_ordem_instavel(inp)

    @staticmethod
    def _avisar_ordem_instavel(inp: InputListarDecisoesFalcao) -> None:
        """Avisa, na ordem padrão, que a coleta junta páginas de uma ordem que varia (ver :meth:`listar_decisoes`)."""
        if inp.ordenacao in (None, "mais_relevante"):
            avisar(
                "A ordem padrão do Falcao (mais_relevante) varia entre chamadas da mesma busca: "
                "páginas requisitadas em momentos diferentes podem repetir ou omitir "
                "documentos. Para coleta de várias páginas, use ordenacao='menos_recente' com "
                "data_juntada_fim fechado no passado, ou confira duplicatas no resultado.",
                UserWarning,
            )

    @staticmethod
    def _avisar_teto(inp: InputListarDecisoesFalcao, total: int) -> None:
        if inp.paginas is None and total >= _MAX_RESULTADOS:
            avisar(
                f"A busca atingiu o teto de {_MAX_RESULTADOS} resultados do Falcao; o "
                "backend nao informa o total real e o resultado pode estar incompleto. "
                "Divida a busca em janelas de data_juntada_inicio/data_juntada_fim.",
                UserWarning,
            )

    @staticmethod
    def _total_paginas(total: int, tamanho_pagina: int) -> int:
        alcancavel = min(total, _MAX_RESULTADOS)
        return max(1, math.ceil(alcancavel / tamanho_pagina))

    @staticmethod
    def _resolver_paginas(paginas, total_paginas: int):
        if paginas is None:
            return range(1, total_paginas + 1)
        if isinstance(paginas, range):
            return range(
                max(1, paginas.start),
                min(paginas.stop, total_paginas + 1),
                paginas.step,
            )
        return [p for p in paginas if 1 <= p <= total_paginas]


def _validar_data(valor, nome: str) -> None:
    """Rejeita a data que ``coerce_brazilian_date`` nao conseguiu converter.

    ``validate_intervalo_datas`` so confere o formato quando os dois limites
    estao presentes. Com um limite so, o valor cru (``""``, ``"abc"``,
    ``"31/02/2024"``) ia para o backend e voltava como HTTP 400 generico.
    """
    try:
        datetime.strptime(valor, _FORMATO_BACKEND)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            f"'{nome}' inválida: {valor!r}. Use DD/MM/AAAA, AAAA-MM-DD ou datetime.date."
        ) from exc
