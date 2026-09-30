"""Metodos de autenticacao que JusBR e PDPJ compartilham."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

import requests
from pydantic import BaseModel, ValidationError

from ...utils.params import raise_on_extra_kwargs
from .cache import carregar_credencial_cache, carregar_credencial_padrao, salvar_credencial
from .credencial import CredencialPdpj
from .login import obter_credencial_govbr
from .renovacao import AuthPdpj

logger = logging.getLogger(__name__)


class PdpjSsoMixin:
    """Login gov.br, cache e renovacao do token do SSO do PJe.

    A classe concreta fornece ``session``, ``token``, ``auth(token)`` e
    ``INPUT_AUTH_GOVBR``, e define em ``NOMES_ENV_TOKEN`` as variaveis de
    ambiente que le, em ordem de precedencia.
    """

    NOMES_ENV_TOKEN: ClassVar[tuple[str, ...]] = ("PDPJ_JWT",)
    INPUT_AUTH_GOVBR: ClassVar[type[BaseModel]]
    session: requests.Session
    token: str | None

    def auth(self, token: str) -> bool:  # pragma: no cover - sobrescrito pelas classes concretas
        """Valida ``token`` e o instala na sessao; cada scraper tem a sua validacao."""
        raise NotImplementedError

    def _instalar_credencial(self, credencial: CredencialPdpj, salvar_renovacao: bool) -> AuthPdpj:
        """Poe a credencial na sessao, com renovacao quando ha refresh token.

        O cabecalho fixo da sessao continua sendo gravado para quem le
        ``session.headers`` diretamente; quem manda na requisicao e o
        :class:`AuthPdpj` em ``session.auth``.
        """

        def ao_renovar(nova: CredencialPdpj) -> None:
            self.token = nova.access_token
            self.session.headers["Authorization"] = f"Bearer {nova.access_token}"
            if salvar_renovacao:
                # Com a gravacao falhando, o cache fica desatualizado e nao pode ser
                # lido: a instancia trocaria o refresh bom, que so ela tem, por um
                # antigo. A leitura volta quando uma gravacao seguinte der certo.
                auth.ler_cache = carregar_credencial_cache if _salvar_sem_derrubar(nova) else None
            logger.info("Token do PDPJ renovado.")

        self.token = credencial.access_token
        self.session.headers["Authorization"] = f"Bearer {credencial.access_token}"
        # Credencial que vive no cache tambem renova pelo cache, para aproveitar
        # a renovacao feita por outra instancia.
        ler_cache = carregar_credencial_cache if salvar_renovacao else None
        auth = AuthPdpj(credencial, ao_renovar, ler_cache)
        self.session.auth = auth
        return auth

    def _carregar_credencial_padrao(self) -> None:
        """Autentica com a primeira credencial valida do ambiente ou do cache."""
        encontrada = carregar_credencial_padrao(self.NOMES_ENV_TOKEN)
        if encontrada is None:
            return
        credencial, veio_do_cache = encontrada
        self._instalar_credencial(credencial, salvar_renovacao=veio_do_cache)

    def auth_govbr(
        self,
        timeout: float = 300.0,
        salvar: bool = True,
        navegador: str | None = None,
        **kwargs: Any,
    ) -> bool:
        """Obtem o token do PDPJ pelo login no gov.br, no Chrome da maquina.

        Abre o portal de servicos do PDPJ no Chrome, Chromium ou Edge
        instalado, com perfil temporario; a pessoa faz o login (CPF, senha,
        captcha e segundo fator) e o metodo captura o token que o portal
        recebe. Com refresh token, as requisicoes seguintes renovam o access
        token sozinhas. Exige navegador com janela, entao nao roda em Colab
        nem em CI; nesses ambientes, use ``auth(token)`` ou a variavel
        ``PDPJ_JWT``.

        Args:
            timeout (float): Segundos para concluir o login. Default ``300``.
            salvar (bool): Grava a credencial em
                ``$XDG_CONFIG_HOME/juscraper/pdpj_token.json`` (ou
                ``~/.config/...``), com permissao ``0600``, para as proximas
                instancias do JusBR e do PDPJ carregarem sem novo login; as
                renovacoes tambem sao gravadas. Default ``True``.
            navegador (str | None): Executavel do Chrome, Chromium ou Edge.
                ``None`` procura um instalado. Default ``None``.

        Returns:
            bool: ``True`` quando o token foi aceito.

        Raises:
            TypeError: Quando um kwarg desconhecido e passado.
            ImportError: Quando falta o extra ``juscraper[govbr]``.
            RuntimeError: Quando nao ha navegador, a janela e fechada ou o
                prazo acaba sem token.
            ValueError: Quando o token capturado e invalido ou ja expirou.

        Exemplo:
            >>> import juscraper as jus
            >>> jusbr = jus.scraper("jusbr")
            >>> jusbr.auth_govbr()
            >>> df = jusbr.cpopg("0000000-00.0000.0.00.0000")

        See also:
            :class:`InputAuthGovbrJusBR` e :class:`InputAuthGovbrPdpj`.
        """
        nome = f"{type(self).__name__}.auth_govbr()"
        try:
            inp = self.INPUT_AUTH_GOVBR(timeout=timeout, salvar=salvar, navegador=navegador, **kwargs)
        except ValidationError as exc:
            raise_on_extra_kwargs(exc, nome, schema_cls=self.INPUT_AUTH_GOVBR)
            raise
        credencial = obter_credencial_govbr(timeout=inp.timeout, navegador=inp.navegador)
        self.auth(credencial.access_token)
        auth = self._instalar_credencial(credencial, salvar_renovacao=inp.salvar)
        if inp.salvar and not _salvar_sem_derrubar(credencial):
            # O cache ficou com a credencial anterior; ler dele trocaria o refresh
            # recem-obtido por um antigo.
            auth.ler_cache = None
        if credencial.refresh_token is None:
            logger.warning(
                "O portal nao entregou refresh token; quando o access token vencer, "
                "sera preciso chamar auth_govbr() de novo."
            )
        return True


def _salvar_sem_derrubar(credencial: CredencialPdpj) -> bool:
    """Grava o cache; uma falha vira aviso, porque a credencial ja esta em uso.

    Sem isso, um diretorio sem permissao de escrita derrubaria um login que deu
    certo, ou a requisicao que disparou a renovacao.
    """
    try:
        caminho = salvar_credencial(credencial)
    except OSError as exc:
        logger.warning("Nao foi possivel gravar o cache do token do PDPJ: %s", exc)
        return False
    logger.info("Token do PDPJ gravado em %s.", caminho)
    return True
