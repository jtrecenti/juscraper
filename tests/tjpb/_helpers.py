"""Helpers compartilhados pelos contratos de jurisprudência do TJPB."""

import responses

from juscraper.courts.tjpb.download import CLASSES_URL

XSRF_COOKIE = "contrato%2Fcsrf"
LARAVEL_COOKIE = "contrato-session"
CLASSES_RESPONSE = [{
    "id_classe_judicial": 53,
    "classe": "AGRAVO DE INSTRUMENTO (202)",
}]


def add_get_classes(*, with_cookie: bool = True) -> None:
    """Registra a resposta do GET de classes e os cookies de sessão do TJPB."""
    headers = (
        [
            ("Set-Cookie", f"XSRF-TOKEN={XSRF_COOKIE}; Path=/"),
            ("Set-Cookie", f"laravel_session={LARAVEL_COOKIE}; Path=/"),
        ]
        if with_cookie else []
    )
    responses.add(
        responses.GET,
        CLASSES_URL,
        json=CLASSES_RESPONSE,
        status=200,
        headers=headers,
    )
