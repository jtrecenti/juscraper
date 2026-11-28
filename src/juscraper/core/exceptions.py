"""Exceções compartilhadas pela infraestrutura HTTP/parse de juscraper.

`RetryExhaustedError` é levantada por `core.http.HTTPScraper._request_with_retry`
quando todas as tentativas de retry esgotaram em status retryable (429/5xx).

`HTTPSemanticError` é a base abstrata para casos de "HTTP-200 com página de erro"
(captcha expirado, sessão inválida, formulário não submetido). Subclasses concretas
ficam nos parsers que detectam o erro, seguindo a **Regra de generalização** de
``CLAUDE.md`` > **Arquitetura**. Página de erro não vira busca vazia: ver
``CONTRIBUTING.md`` > **Falhas HTTP, falhas por linha e coleta parcial** >
**Falha por linha**.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import pandas as pd


class _RecriaSemInit(Exception):
    """Base das exceções cujo ``__init__`` pede outros argumentos que não a mensagem.

    ``args`` só guarda a mensagem: sem o ``__reduce__`` abaixo, pickle e
    ``copy`` chamariam ``__init__(mensagem)`` e quebrariam, o que perderia o
    erro numa coleta rodada em ``ProcessPoolExecutor``. O erro é recriado sem
    passar pelo ``__init__``, e os atributos e a causa encadeada voltam pelo
    estado serializado; vale também para as subclasses com ``__init__`` próprio.
    """

    def __reduce__(self) -> tuple[object, ...]:
        """Recria o erro com ``args``, atributos e causa, sem o ``__init__``."""
        return (_recriar_sem_init, (type(self), *self.args), (self.__dict__, self.__cause__))

    def __setstate__(self, state: object) -> None:
        """Restaura também pickles anteriores, cujo estado era só o dicionário."""
        if state is None:
            return
        if isinstance(state, dict):
            self.__dict__.update(state)
            return
        atributos, causa = cast("tuple[dict[str, object], BaseException | None]", state)
        self.__dict__.update(atributos)
        self.__cause__ = causa


def _recriar_sem_init(cls: type[BaseException], *args: object) -> BaseException:
    # ``BaseException.__new__`` já guarda ``args``; o ``__init__`` fica de fora.
    return cls.__new__(cls, *args)


class RetryExhaustedError(_RecriaSemInit):
    """Levantada quando ``_request_with_retry`` esgota o número de tentativas."""

    def __init__(self, status_code: int | None, attempts: int):
        self.status_code = status_code
        self.attempts = attempts
        super().__init__(
            f"HTTP request failed after {attempts} attempts (last status: {status_code})"
        )


class HTTPSemanticError(Exception):
    """Base para respostas HTTP-200 semanticamente erradas (página de erro disfarçada)."""


class PaginaInesperadaError(_RecriaSemInit, HTTPSemanticError, ValueError, RuntimeError):
    """A resposta não é a página que o fluxo espera, ou contradiz a contagem da busca.

    Levantada pelos helpers de :mod:`juscraper.utils.pagination` que conferem
    cada resposta antes de se ler algo dela: ``exigir_pagina`` (página de
    outro tipo, como formulário, sessão expirada ou etapa intermediária),
    ``ConferenciaDePaginas`` e ``baixar_paginas_pedidas`` (página dentro do total
    sem itens, ou que repete uma anterior) e ``resolve_total_pages``
    (contagem ausente ou menor que as linhas da página). Sem a conferência,
    essas respostas viram busca vazia ou coleta menor sem erro.

    Vira o motivo :data:`juscraper.core.failures.MOTIVO_RESPOSTA_INESPERADA`.
    Herda de ``ValueError`` e de ``RuntimeError``, os erros que esses
    caminhos levantavam antes dela, para que o ``except`` de quem já os
    capturava continue valendo.

    Attributes:
        tribunal: Sigla do tribunal ou nome do agregador.
        etapa: Onde a conferência falhou (``"contagem"``, ``"paginação"``,
            ``"cjsg"``, ``"passo 3: escolha do tipo"``).
        pagina: Página da busca, quando a etapa é paginada.
        url: Endereço da resposta, quando conhecido.
    """

    def __init__(
        self,
        mensagem: str,
        *,
        tribunal: str,
        etapa: str,
        pagina: int | None = None,
        url: str | None = None,
    ):
        self.tribunal = tribunal
        self.etapa = etapa
        self.pagina = pagina
        self.url = url
        super().__init__(mensagem)


class CaptchaEsgotadoError(HTTPSemanticError, RuntimeError):
    """O portal recusou o captcha resolvido em todas as tentativas de uma consulta.

    Vira o motivo :data:`juscraper.core.failures.MOTIVO_CAPTCHA_ESGOTADO`.
    Herda de ``RuntimeError``, que era o erro levantado antes dela.
    """


class BotChallengeBlockedError(_RecriaSemInit):
    """Levantada quando um portal bloqueia o request via bot manager (ex.: Akamai, CloudFront).

    O sintoma típico é HTTP 403 com body curto ``Access Denied`` e uma referência
    Akamai (``Reference #...``); o cookie de challenge (``ak_bmsc``) nem chega
    a ser emitido. Isso normalmente significa que o IP do cliente foi
    rate-limited — não adianta retentar com a mesma sessão.

    Mensagem orienta o usuário a aguardar alguns minutos antes de tentar de
    novo, ou trocar de IP (VPN, hotspot). O bloqueio é session-wide: nenhum
    item do batch vai conseguir passar. Os métodos com ``motivo_falha`` por
    linha a registram como linha (ver
    :data:`juscraper.core.failures.MOTIVO_BLOQUEIO_ANTI_BOT`); os demais a
    propagam.

    ``bot_manager`` nomeia o bloqueador na mensagem. O default é ``"Akamai"``
    (TRFs); o agregador Falcao passa ``"CloudFront"``, cujo 403 é uma página
    HTML ``The request could not be satisfied`` servida pelo próprio CDN, e
    :class:`WafChallengeError` e o TJTO passam ``"AWS WAF"``.

    ``mensagem`` substitui o texto padrão, que descreve o 403: as subclasses
    cujo sintoma é outro (desafio JavaScript com HTTP 200, cookie que não
    resolve o desafio) passam a própria mensagem.
    """

    def __init__(
        self,
        tribunal: str,
        url: str,
        reference: str | None = None,
        *,
        bot_manager: str = "Akamai",
        mensagem: str | None = None,
    ):
        self.tribunal = tribunal
        self.url = url
        self.reference = reference
        self.bot_manager = bot_manager
        if mensagem is None:
            mensagem = (
                f"{tribunal} bloqueou a requisição (HTTP 403) em {url}. "
                f"Provavelmente foi o bot manager ({bot_manager}) limitando "
                f"o seu IP — aguarde alguns minutos antes de tentar de novo "
                f"ou troque de IP (VPN, hotspot)."
            )
            if reference:
                mensagem += f" Reference: {reference}."
        super().__init__(mensagem)


class BloqueioAntiBotWarning(UserWarning):
    """Aviso agregado de um lote em que alguma linha saiu com ``bloqueio_anti_bot``.

    Os métodos com ``motivo_falha`` por linha registram o
    :class:`BotChallengeBlockedError` na linha e emitem um único aviso ao fim
    (:func:`juscraper.core.failures.avisar_falhas`). Quando alguma das falhas é
    um bloqueio anti-bot, o aviso sai nesta categoria, mesmo que a mensagem não
    cite essa linha entre os exemplos. Por herdar de ``UserWarning``, os filtros
    existentes continuam valendo; para tratar só o bloqueio, filtre por esta
    classe (``warnings.simplefilter("error", BloqueioAntiBotWarning)``).
    """


class WafChallengeError(BotChallengeBlockedError):
    """Levantada quando o AWS WAF desafia de novo logo depois de o cookie ser renovado.

    O desafio JavaScript do AWS WAF se resolve com o cookie ``aws-waf-token``
    (ver :mod:`juscraper.core.waf`). Se a requisição repetida com o cookie novo
    volta a receber o desafio, o WAF está recusando a sessão inteira, e nenhum
    item do batch passaria. Herda de :class:`BotChallengeBlockedError` para ser
    tratada pelos mesmos ``try/except`` por item.

    Também sai quando o cookie não pôde ser obtido (navegador ausente, cookie
    não emitido no prazo): sem ele, nenhuma requisição desafiada passaria, e
    tentar de novo a cada item relançaria o navegador.
    """

    def __init__(self, tribunal: str, url: str, motivo: str | None = None):
        if motivo is None:
            mensagem = (
                f"O WAF do {tribunal} desafiou de novo logo apos a renovacao do cookie "
                f"aws-waf-token em {url}. Aguarde alguns minutos antes de tentar outra vez."
            )
        else:
            mensagem = f"O WAF do {tribunal} desafiou em {url}, e o cookie aws-waf-token nao foi obtido: {motivo}"
        super().__init__(tribunal, url, bot_manager="AWS WAF", mensagem=mensagem)


class ColetaParcialError(_RecriaSemInit, RuntimeError):
    """Levantada quando parte de uma coleta falha e o resultado ficaria incompleto.

    O auto-chunk do eSAJ divide a busca em janelas de data. Devolver só as
    janelas que passaram faria o resultado parcial se passar por completo (no
    TJAC, 1 acórdão em vez de 46, com um ``UserWarning`` que notebook não
    mostra). Por isso a falha sobe, e o trabalho já feito vem no próprio erro:

    * ``resultado``: DataFrame das janelas que passaram, deduplicado;
    * ``falhas``: lista de ``(inicio, fim, excecao)`` das janelas que falharam.

    O ``listar_processos`` do DataJud usa o mesmo erro quando a paginação de
    um alias para no meio: os demais aliases ainda são consultados,
    ``resultado`` traz tudo o que veio de todos eles, e cada item de
    ``falhas`` vem como ``(None, None, excecao)``; o alias e a página estão
    na mensagem.

    O ``cjpg`` do TJSP também o levanta quando parte das páginas baixadas não
    pode ser lida: ``resultado`` traz as páginas lidas, e cada item de
    ``falhas`` vem como ``(None, None, excecao)``, com o arquivo na mensagem.

    O ``cjsg`` do TJMG, o do TJPR, o do TJRS e o ``cjsg``/``cjpg`` do TJTO o
    levantam quando uma página falha depois das tentativas (no TJTO, também
    pelo bloqueio do AWS WAF; no TJRS, também pelo erro do Solr no lugar dos
    resultados): a busca para ali, ``resultado`` traz as páginas anteriores, e
    ``falhas`` tem um item ``(None, None, excecao)``; as páginas que faltam
    estão na mensagem.

    O ``__cause__`` é a exceção da primeira falha.
    """

    def __init__(
        self, mensagem: str, *, resultado: pd.DataFrame, falhas: list[tuple[str | None, str | None, Exception]]
    ):
        super().__init__(mensagem)
        self.resultado = resultado
        self.falhas = falhas


class InvalidJSONResponseError(_RecriaSemInit, HTTPSemanticError):
    """Resposta com status < 400 cujo corpo não é JSON válido, mesmo após retries.

    Levantada por ``HTTPScraper._request_with_retry`` quando chamado com
    ``expect_json=True`` e o backend devolve corpo vazio/não-JSON num status de
    sucesso de forma persistente (ex.: o backend Solr do TJES devolve
    esporadicamente HTTP 200 com corpo vazio — ver #275). Substitui o
    ``json.JSONDecodeError`` opaco por um erro com contexto da requisição.
    """

    def __init__(
        self,
        url: str,
        status_code: int,
        attempts: int,
        content_type: str | None = None,
        snippet: str | None = None,
    ):
        self.url = url
        self.status_code = status_code
        self.attempts = attempts
        self.content_type = content_type
        self.snippet = snippet
        msg = (
            f"Resposta sem JSON válido em {url} após {attempts} tentativa(s) "
            f"(status {status_code}, content-type {content_type!r})."
        )
        if snippet and snippet.strip():
            msg += f" Início do corpo: {snippet!r}"
        super().__init__(msg)
