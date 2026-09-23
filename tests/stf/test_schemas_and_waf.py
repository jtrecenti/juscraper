"""Schema domain checks and WAF token helper for STF."""
import sys

import pytest
from pydantic import ValidationError

from juscraper.courts.stf._waf import obter_waf_token
from juscraper.courts.stf.schemas import InputContarDecisoesSTF, InputListarDecisoesSTF


def test_tamanho_pagina_acima_de_250_e_rejeitado():
    with pytest.raises(ValidationError):
        InputListarDecisoesSTF(pesquisa="*", tamanho_pagina=251)


def test_base_fora_do_dominio_e_rejeitada():
    with pytest.raises(ValidationError):
        InputContarDecisoesSTF(pesquisa="*", base="informativos")


def test_defaults():
    inp = InputListarDecisoesSTF(pesquisa="*")
    assert (inp.base, inp.classe, inp.inteiro_teor, inp.tamanho_pagina) == ("decisoes", None, False, 250)


def test_contar_nao_aceita_tamanho_pagina():
    with pytest.raises(ValidationError):
        InputContarDecisoesSTF(pesquisa="*", tamanho_pagina=10)


def test_sem_playwright_orienta_a_instalar_o_extra(mocker):
    mocker.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None})
    with pytest.raises(ImportError, match=r"juscraper\[stf\]"):
        obter_waf_token()
