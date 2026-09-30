"""Offline contract tests for JusbrScraper.auth.

``auth(token)`` apenas decodifica o JWT (sem verificar assinatura) e seta o
header ``Authorization: Bearer <token>`` na sessao quando o token e valido.
Nao dispara nenhuma request HTTP, entao os testes aqui nao usam ``responses``.

``verify_exp=True`` foi tornado explicito no ``client.py`` (followup 1 da
#141): com ``verify_signature=False`` o PyJWT desativa ``verify_exp`` por
padrao e o ramo ``except jwt.ExpiredSignatureError`` virava dead code. Agora
tokens expirados levantam ``ValueError("Token JWT expirado.")`` como
documentado.
"""
import io
import json

import jwt
import pytest
import requests

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises

# PyJWT emite ``InsecureKeyLengthWarning`` para chaves HMAC < 32 bytes em SHA256;
# o ``filterwarnings = ["error"]`` do pytest converte isso em falha. Chave de 32+
# bytes evita ruido sem afetar o contrato (auth nao verifica assinatura).
_HMAC_KEY = "0123456789abcdef0123456789abcdef-test"


def _token(claims: dict) -> str:
    """Build a structurally valid JWT with the given claims (HS256)."""
    encoded: str = jwt.encode(claims, _HMAC_KEY, algorithm="HS256")
    return encoded


def test_auth_token_valido_seta_header():
    scraper = jus.scraper("jusbr")
    token = _token({"sub": "tester", "exp": 9999999999})

    assert scraper.auth(token) is True
    assert scraper.session.headers["authorization"] == f"Bearer {token}"
    assert scraper.token == token


def test_auth_token_expirado_levanta_value_error():
    """Token com ``exp`` no passado levanta ``ValueError("Token JWT expirado.")``.

    Garantido pelo ``"verify_exp": True`` explicito nas options do
    ``jwt.decode`` em ``client.py:auth`` (followup 1 da #141).
    """
    scraper = jus.scraper("jusbr")
    expired = _token({"sub": "tester", "exp": 0})

    with pytest.raises(ValueError, match="expirado"):
        scraper.auth(expired)
    assert "authorization" not in scraper.session.headers
    assert scraper.token is None


def test_auth_token_sem_exp_passa_silencioso():
    """Token sem claim ``exp`` e aceito sem erro.

    O PyJWT so valida quando o claim existe. Header e setado e ``auth`` retorna ``True``.
    """
    scraper = jus.scraper("jusbr")
    no_exp = _token({"sub": "tester"})

    assert scraper.auth(no_exp) is True
    assert scraper.token == no_exp
    assert scraper.session.headers["authorization"] == f"Bearer {no_exp}"


def test_auth_token_malformado_levanta_value_error():
    """String que nao e JWT estrutural levanta ``ValueError``.

    Ela cai em ``InvalidTokenError`` no ``jwt.decode``, e o ``except`` re-levanta como ``ValueError``.
    """
    scraper = jus.scraper("jusbr")

    with pytest.raises(ValueError, match=r"inv[áa]lido"):
        scraper.auth("not-a-jwt")
    assert "authorization" not in scraper.session.headers
    assert scraper.token is None


def test_auth_kwarg_desconhecido_levanta_type_error():
    """Kwarg desconhecido vira ``TypeError`` canonico via ``InputAuthJusBR`` wirado.

    A validacao do schema precede o ``jwt.decode``, entao o ``TypeError`` sai
    mesmo com um token estruturalmente valido.
    """
    scraper = jus.scraper("jusbr")
    assert_unknown_kwarg_raises(
        scraper.auth, "kwarg_inventado", _token({"sub": "tester", "exp": 9999999999})
    )


# ---------------------------------------------------------------------------
# Construtor com token= e auth() que falha
# ---------------------------------------------------------------------------


def test_construtor_valida_token_pelo_auth():
    token = _token({"sub": "tester", "exp": 9999999999})
    scraper = jus.scraper("jusbr", token=token)
    assert scraper.token == token
    assert scraper.session.headers["authorization"] == f"Bearer {token}"


@pytest.mark.parametrize(
    ("token", "mensagem"),
    [(_token({"sub": "tester", "exp": 0}), "expirado"), ("not-a-jwt", r"inv[áa]lido"), ("", r"inv[áa]lido")],
    ids=["vencido", "malformado", "vazio"],
)
def test_construtor_com_token_recusado_levanta_value_error(token, mensagem):
    with pytest.raises(ValueError, match=mensagem):
        jus.scraper("jusbr", token=token)


@pytest.mark.parametrize(
    "recusado", [_token({"sub": "tester", "exp": 0}), "not-a-jwt"], ids=["vencido", "malformado"],
)
def test_auth_recusado_preserva_token_e_header_anteriores(recusado):
    valido = _token({"sub": "tester", "exp": 9999999999})
    scraper = jus.scraper("jusbr", token=valido)
    auth_anterior = scraper.session.auth

    with pytest.raises(ValueError, match="Token JWT"):
        scraper.auth(recusado)

    assert scraper.token == valido
    assert scraper.session.headers["authorization"] == f"Bearer {valido}"
    # Quem põe o Authorization enviado é o AuthPdpj em session.auth.
    assert scraper.session.auth is auth_anterior


# ---------------------------------------------------------------------------
# auth_firefox, com a sessão do SSO simulada
# ---------------------------------------------------------------------------

_LOCATION_COM_CODE = "https://portaldeservicos.pdpj.jus.br/home#state=1234&code=codigo-sso"


def _resposta(status: int = 200, headers: dict | None = None, corpo=None, texto: str | None = None):
    resp = requests.Response()
    resp.status_code = status
    resp.headers.update(headers or {})
    # O corpo entra pelo ``raw``, como o requests lê de uma conexão.
    resp.raw = io.BytesIO(json.dumps(corpo).encode() if corpo is not None else (texto or "").encode())
    return resp


@pytest.fixture
def preparar_sso(mocker):
    """Cria o scraper e depois simula a sessão avulsa que ``auth_firefox`` abre.

    A ordem importa: o patch de ``requests.Session`` alcançaria também a
    sessão do próprio scraper, se ele fosse criado depois.
    """
    def preparar(**kwargs):
        scraper = jus.scraper("jusbr", **kwargs)
        mocker.patch("juscraper.aggregators.jusbr.client.browser_cookie3.firefox", return_value={})
        sessao = mocker.MagicMock()
        mocker.patch("juscraper.aggregators.jusbr.client.requests.Session", return_value=sessao)
        return scraper, sessao
    return preparar


def test_auth_firefox_troca_o_code_pelo_token_e_passa_pelo_auth(preparar_sso):
    token = _token({"sub": "tester", "exp": 9999999999})
    scraper, sessao_sso = preparar_sso()
    sessao_sso.get.return_value = _resposta(302, {"Location": _LOCATION_COM_CODE})
    sessao_sso.post.return_value = _resposta(corpo={"access_token": token})

    assert scraper.auth_firefox() is True

    assert scraper.token == token
    assert scraper.session.headers["authorization"] == f"Bearer {token}"
    assert sessao_sso.post.call_args.kwargs["data"]["code"] == "codigo-sso"
    assert sessao_sso.get.call_args.kwargs["timeout"] == 15
    assert sessao_sso.post.call_args.kwargs["timeout"] == 15


def test_auth_firefox_usa_timeout_da_politica(preparar_sso):
    scraper, sessao_sso = preparar_sso(politica={"listagem": {"timeout": 4}})
    sessao_sso.get.return_value = _resposta(302, {"Location": _LOCATION_COM_CODE})
    sessao_sso.post.return_value = _resposta(corpo={"access_token": _token({"sub": "t"})})

    scraper.auth_firefox()

    assert sessao_sso.get.call_args.kwargs["timeout"] == 4


def test_auth_firefox_sem_location_levanta_runtime_error(preparar_sso):
    scraper, sessao_sso = preparar_sso()
    sessao_sso.get.return_value = _resposta(200)
    with pytest.raises(RuntimeError, match="Location"):
        scraper.auth_firefox()


def test_auth_firefox_sem_code_levanta_runtime_error(preparar_sso):
    scraper, sessao_sso = preparar_sso()
    sessao_sso.get.return_value = _resposta(302, {"Location": "https://x.test/home#error=login_required"})
    with pytest.raises(RuntimeError, match="code"):
        scraper.auth_firefox()


@pytest.mark.parametrize(
    "resposta",
    [
        _resposta(400, corpo={"error": "invalid_grant"}),
        _resposta(200, texto="<html>erro</html>"),
        _resposta(200, corpo=["access_token"]),
    ],
    ids=["sem-chave", "sem-json", "lista"],
)
def test_auth_firefox_sem_access_token_levanta_runtime_error(preparar_sso, resposta):
    scraper, sessao_sso = preparar_sso()
    sessao_sso.get.return_value = _resposta(302, {"Location": _LOCATION_COM_CODE})
    sessao_sso.post.return_value = resposta

    with pytest.raises(RuntimeError, match="access_token"):
        scraper.auth_firefox()
    assert scraper.token is None


def test_auth_firefox_token_vencido_levanta_value_error(preparar_sso):
    scraper, sessao_sso = preparar_sso()
    sessao_sso.get.return_value = _resposta(302, {"Location": _LOCATION_COM_CODE})
    sessao_sso.post.return_value = _resposta(corpo={"access_token": _token({"sub": "t", "exp": 0})})

    with pytest.raises(ValueError, match="expirado"):
        scraper.auth_firefox()
    assert scraper.token is None
