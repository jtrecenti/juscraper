"""403 que nao e limite da API segue o retry do HTTPScraper."""
import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import RetryExhaustedError
from juscraper.courts.stf.download import BASE_URL


@pytest.mark.parametrize(
    "resposta",
    [
        {"json": {"message": "Forbidden"}},
        {"body": "<html>Request blocked</html>", "content_type": "text/html"},
    ],
    ids=["json-sem-detail", "corpo-nao-json"],
)
@responses.activate
def test_403_sem_detail_e_retentado_ate_esgotar(mocker, resposta):
    mocker.patch("time.sleep")
    responses.add(responses.POST, BASE_URL, status=403, **resposta)

    with pytest.raises(RetryExhaustedError):
        jus.scraper("stf", waf_token="token-de-teste").listar_decisoes("pejotização", paginas=1)

    assert len(responses.calls) == 3
