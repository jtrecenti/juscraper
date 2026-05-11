"""Filter-propagation contract for TJSP cjpg (refs #84, #104 comment)."""
import pandas as pd
import responses
from responses.matchers import query_param_matcher

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises, load_sample_bytes
from tests.fixtures.capture._util import make_tjsp_cjpg_params

BASE = "https://esaj.tjsp.jus.br/cjpg"

# Fully populated filter set. ``id_processo`` is a CNJ — the scraper
# normalizes it via ``clean_cnj`` before sending, so we pass the raw
# formatted value here and let production decide the params.
_CLASSES: list[str] = ["cls-value"]
_ASSUNTOS: list[str] = ["subj-value"]
_VARAS: list[str] = ["vara-value"]
_ID_PROCESSO = "1000123-45.2023.8.26.0100"
_DATA_INI = "01/01/2024"
_DATA_FIM = "31/03/2024"


@responses.activate
def test_cjpg_all_filters_land_in_query_params(tmp_path, mocker):
    mocker.patch("time.sleep")
    # ``clean_cnj`` strips punctuation from id_processo — mirror that here.
    from juscraper.utils.cnj import clean_cnj
    id_processo_clean = clean_cnj(_ID_PROCESSO)
    expected = make_tjsp_cjpg_params(
        pesquisa="dano moral",
        id_processo=id_processo_clean,
        classes=_CLASSES,
        assuntos=_ASSUNTOS,
        varas=_VARAS,
        data_inicio=_DATA_INI,
        data_fim=_DATA_FIM,
    )
    # requests drops keys whose value is None
    expected = {k: v for k, v in expected.items() if v is not None}
    responses.add(
        responses.GET,
        f"{BASE}/pesquisar.do",
        body=load_sample_bytes("tjsp", "cjpg/no_results.html"),
        status=200,
        content_type="text/html; charset=utf-8",
        match=[query_param_matcher(expected)],
    )

    df = jus.scraper("tjsp", download_path=str(tmp_path)).cjpg(
        "dano moral",
        paginas=1,
        classes=_CLASSES,
        assuntos=_ASSUNTOS,
        varas=_VARAS,
        id_processo=_ID_PROCESSO,
        data_julgamento_inicio=_DATA_INI,
        data_julgamento_fim=_DATA_FIM,
    )
    assert isinstance(df, pd.DataFrame)


def test_cjpg_unknown_kwarg_raises(tmp_path):
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    assert_unknown_kwarg_raises(scraper.cjpg, "parametro_bobo", "dano moral", paginas=1)


def test_cjpg_rejects_cjsg_fields(tmp_path):
    """cjpg takes plural lists, not cjsg's singular ementa/classe/comarca."""
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))
    for bad in ("ementa", "classe", "comarca", "orgao_julgador", "baixar_sg"):
        assert_unknown_kwarg_raises(scraper.cjpg, bad, "dano moral", paginas=1)
