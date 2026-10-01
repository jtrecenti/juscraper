"""Consulta pública do PJe de 1º grau do TJPE (``cpopg``).

O 1º grau do TJPE roda o PJe ConsultaPública, o mesmo sistema dos TRFs, então
o fluxo de busca, detalhe e peças vem inteiro de
:class:`juscraper.courts._trf.base.TRFConsultaScraper`. O que o TJPE tem de
próprio é o AWS WAF na frente do site: ele desafia de forma intermitente, com
HTTP 202 e uma página de JavaScript no lugar da resposta pedida. Por isso o
cookie ``aws-waf-token`` é obtido só quando o desafio aparece, e a sessão
segue em ``requests`` enquanto o WAF deixa passar, sem exigir o Playwright.

O reCAPTCHA que a página carrega está desligado no servidor
(``if (false) { grecaptcha.execute(); }``); se for ligado, a busca passa a
voltar sem resultado e este módulo precisa mudar.
"""
from __future__ import annotations

from typing import Any

import requests

from juscraper.core.exceptions import WafChallengeError
from juscraper.core.waf import USER_AGENT, WAF_COOKIE, eh_desafio_waf, obter_waf_token

from .._trf.base import TRFConsultaScraper
from .._trf.download import LISTVIEW_PATH


class TJPEConsultaPublicaScraper(TRFConsultaScraper):
    """PJe ConsultaPública de 1º grau do TJPE, com o cookie do AWS WAF sob demanda."""

    BASE_URL = "https://pje.cloud.tjpe.jus.br/1g/"
    TRIBUNAL_NAME = "TJPE"

    def _configure_session(self, session: requests.Session) -> None:
        super()._configure_session(session)
        # O WAF amarra o cookie ao user agent do navegador que resolveu o desafio.
        session.headers["User-Agent"] = USER_AGENT

    def _renovar_cookie_waf(self) -> None:
        token = obter_waf_token(self.BASE_URL + LISTVIEW_PATH, tribunal=self.TRIBUNAL_NAME)
        self.session.cookies.set(WAF_COOKIE, token)

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Repete a requisição uma vez com cookie novo quando o WAF desafia.

        Todo HTTP da família ``_trf`` passa por aqui, inclusive o POST da busca
        e o GET das peças no meio da conversa Seam; repetir a mesma requisição
        na mesma sessão preserva o ``JSESSIONID`` e os tokens ``ca``.
        """
        resp = super()._request_with_retry(method, url, **kwargs)
        if not eh_desafio_waf(resp):
            return resp
        self._renovar_cookie_waf()
        resp = super()._request_with_retry(method, url, **kwargs)
        if eh_desafio_waf(resp):
            raise WafChallengeError(self.TRIBUNAL_NAME, url)
        return resp
