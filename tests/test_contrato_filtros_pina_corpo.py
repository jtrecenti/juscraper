"""Contrato de filtros com matcher derivado do builder precisa ler o corpo enviado.

Um matcher montado com o mesmo builder que o raspador usa
(``json_params_matcher(build_cjsg_payload(...))``) confere que o raspador chama
o builder, mas não o que o builder produz: trocar uma chave do backend no
builder passa sem reprovar (issue #514; o caso do TJRO foi o #438, corrigido no
#512). Nesses arquivos, alguma asserção tem de ler a requisição enviada
(``request.body``, ``request.params`` ou ``request.url``) e compará-la com os
nomes de campo do backend escritos à mão.
"""
import re
from pathlib import Path

import pytest

RAIZ_TESTES = Path(__file__).resolve().parent

MATCHER_DO_BUILDER = re.compile(
    r"(?:json_params_matcher|urlencoded_params_matcher|query_param_matcher)\(\s*build_"
)
LE_REQUISICAO = re.compile(r"\.request\.(?:body|params|url)\b")


def _contratos_com_matcher_do_builder() -> list[Path]:
    return sorted(
        caminho
        for caminho in RAIZ_TESTES.glob("*/test_*filters_contract.py")
        if MATCHER_DO_BUILDER.search(caminho.read_text(encoding="utf-8"))
    )


def test_ha_contratos_com_matcher_do_builder():
    """Sem candidatos, o teste abaixo passaria vazio se o padrão de busca quebrasse."""
    assert _contratos_com_matcher_do_builder()


@pytest.mark.parametrize(
    "caminho",
    _contratos_com_matcher_do_builder(),
    ids=lambda caminho: str(caminho.relative_to(RAIZ_TESTES)),
)
def test_contrato_de_filtros_le_o_corpo_enviado(caminho):
    assert LE_REQUISICAO.search(caminho.read_text(encoding="utf-8")), (
        f"{caminho.relative_to(RAIZ_TESTES)} monta o matcher com o próprio builder e "
        "nenhuma asserção lê a requisição enviada. Confira o corpo (ou a query) "
        "contra um dicionário literal com os nomes de campo do backend, como em "
        "tests/tjro/test_cjsg_filters_contract.py."
    )
