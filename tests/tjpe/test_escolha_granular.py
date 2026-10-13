"""Caracterização da seleção de botões na página de escolha do TJPE.

Os casos partem da página capturada (``cjsg/step_02_escolha.html``): os de
borda alteram um trecho dela por vez. HTML escrito à mão fica restrito às
guardas que a página real não permite provocar.
"""

import pytest

from juscraper.courts.tjpe.download import extract_escolha_button_id
from tests._helpers import load_sample

# Trechos da captura. Se o sample for recapturado e algum deles mudar,
# ``_trocar`` falha apontando o trecho, em vez de deixar o caso passar sem ter
# alterado a página.
ID_ACORDAOS = "resultadoForm:j_id27"
ID_MONOCRATICAS = "resultadoForm:j_id37"
ROTULO = "<label>\nAc&oacute;rd&atilde;os</label>"
PAR = f"{{'{ID_ACORDAOS}':'{ID_ACORDAOS}'}}"
ONCLICK = (
    " onclick=\"if(typeof jsfcljs == 'function'){jsfcljs(document.getElementById('resultadoForm'),"
    f"{PAR},'');}}return false\""
)
TEXTO = "953 documentos encontrados"
CELULA_DO_LINK = '<td class="text-right"><a'

ID_COPIA = "resultadoForm:copia"
LINK_MINIMO = "<a onclick=\"{'id':'id'}\">1 documentos encontrados</a>"

# Cada entrada tira da linha de acórdãos uma das condições que a tornam o
# botão procurado.
LINHAS_INVALIDAS = [
    pytest.param([(ROTULO, "Ac&oacute;rd&atilde;os")], id="rotulo_sem_label"),
    pytest.param(
        [
            (ROTULO, "Ac&oacute;rd&atilde;os"),
            (CELULA_DO_LINK, '<td class="text-right"><label>Ac&oacute;rd&atilde;os</label><a'),
        ],
        id="label_fora_da_primeira_celula",
    ),
    pytest.param(
        [(ROTULO, "<label>\nAc&oacute;rd&atilde;os e S&uacute;mulas</label>")],
        id="rotulo_que_so_contem_o_tipo",
    ),
    pytest.param([(TEXTO, "953 Documentos encontrados")], id="texto_em_outra_caixa"),
    pytest.param([(ONCLICK, "")], id="link_sem_onclick"),
    pytest.param([(PAR, "{}")], id="onclick_sem_par"),
]


def _trocar(texto: str, trocas: list[tuple[str, str]]) -> str:
    """Aplica as trocas, exigindo que cada trecho exista uma única vez."""
    for antigo, novo in trocas:
        assert texto.count(antigo) == 1, f"trecho ausente ou repetido na captura: {antigo!r}"
        texto = texto.replace(antigo, novo)
    return texto


def _pagina() -> str:
    return load_sample("tjpe", "cjsg/step_02_escolha.html")


def _linha_acordaos(pagina: str) -> str:
    inicio = pagina.index("<tr>")
    linha = pagina[inicio:pagina.index("</tr>", inicio) + len("</tr>")]
    assert ROTULO in linha, "a primeira linha da captura deixou de ser a de acórdãos"
    return linha


def _com_linha_trocada(nova_linha: str) -> str:
    pagina = _pagina()
    return _trocar(pagina, [(_linha_acordaos(pagina), nova_linha)])


def _linha_copia() -> str:
    """Segunda linha de acórdãos, válida, com outro identificador."""
    return _trocar(_linha_acordaos(_pagina()), [(PAR, f"{{'{ID_COPIA}':'{ID_COPIA}'}}")])


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [("Acórdãos", ID_ACORDAOS), ("Decisões Monocráticas", ID_MONOCRATICAS)],
)
def test_escolha_pagina_capturada(tipo, esperado):
    assert extract_escolha_button_id(_pagina(), tipo) == esperado


def test_escolha_tipo_padrao():
    assert extract_escolha_button_id(_pagina()) == ID_ACORDAOS


@pytest.mark.parametrize("tipo", ["acórdãos", "Acórdãos ", "Acórdão", "Decisões", "Sentenças"])
def test_escolha_exige_rotulo_exato(tipo):
    with pytest.raises(ValueError) as erro:
        extract_escolha_button_id(_pagina(), tipo)
    assert str(erro.value) == f"Could not find escolha button for '{tipo}'"


@pytest.mark.parametrize("trocas", LINHAS_INVALIDAS)
def test_escolha_linha_invalida_nao_serve(trocas):
    html = _com_linha_trocada(_trocar(_linha_acordaos(_pagina()), trocas))
    with pytest.raises(ValueError, match="Could not find escolha button for 'Acórdãos'"):
        extract_escolha_button_id(html)


@pytest.mark.parametrize("trocas", LINHAS_INVALIDAS)
def test_escolha_pula_linha_invalida_e_segue(trocas):
    invalida = _trocar(_linha_acordaos(_pagina()), trocas)
    html = _com_linha_trocada(invalida + _linha_copia())
    assert extract_escolha_button_id(html) == ID_COPIA


def test_escolha_primeira_linha_valida_vence():
    html = _com_linha_trocada(_linha_acordaos(_pagina()) + _linha_copia())
    assert extract_escolha_button_id(html) == ID_ACORDAOS


@pytest.mark.parametrize(
    ("trocas", "esperado"),
    [
        pytest.param([(TEXTO, f"<span>{TEXTO}</span>")], ID_ACORDAOS, id="texto_dentro_de_span"),
        pytest.param(
            [(PAR, "{'resultadoForm:primeiro':'valor','resultadoForm:segundo':'outro'}")],
            "resultadoForm:primeiro",
            id="chave_do_primeiro_par",
        ),
    ],
)
def test_escolha_variacoes_validas(trocas, esperado):
    html = _com_linha_trocada(_trocar(_linha_acordaos(_pagina()), trocas))
    assert extract_escolha_button_id(html) == esperado


@pytest.mark.parametrize(
    "html",
    [
        pytest.param("", id="vazio"),
        pytest.param(LINK_MINIMO, id="link_fora_de_td"),
        pytest.param(f"<td>{LINK_MINIMO}</td>", id="td_fora_de_tr"),
    ],
)
def test_escolha_estrutura_incompleta(html):
    with pytest.raises(ValueError, match="Could not find escolha button for 'Acórdãos'"):
        extract_escolha_button_id(html)


def test_escolha_tipo_vazio_aceita_linha_sem_label():
    html = f"<tr><td>Sem label</td><td>{LINK_MINIMO}</td></tr>"
    assert extract_escolha_button_id(html, "") == "id"
