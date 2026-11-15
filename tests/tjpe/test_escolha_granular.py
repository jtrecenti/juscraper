"""Caracterização da seleção de botões na página de escolha do TJPE.

Os casos partem da página capturada (``cjsg/step_02_escolha.html``). Os de
borda trocam trechos da linha de acórdãos dela por fragmentos escritos no
teste; a página inteira só é escrita à mão em
``test_escolha_estrutura_incompleta``, que repete as guardas de estrutura sem
nenhuma marcação ao redor.
"""

import re

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
LINHAS_INVALIDAS: dict[str, list[tuple[str, str]]] = {
    "rotulo_sem_label": [(ROTULO, "Ac&oacute;rd&atilde;os")],
    "label_fora_da_primeira_celula": [
        (ROTULO, "Ac&oacute;rd&atilde;os"),
        (CELULA_DO_LINK, '<td class="text-right"><label>Ac&oacute;rd&atilde;os</label><a'),
    ],
    "rotulo_que_so_contem_o_tipo": [(ROTULO, "<label>\nAc&oacute;rd&atilde;os e S&uacute;mulas</label>")],
    "texto_em_outra_caixa": [(TEXTO, "953 Documentos encontrados")],
    "link_sem_onclick": [(ONCLICK, "")],
    "onclick_sem_par": [(PAR, "{}")],
    "link_fora_de_td": [(CELULA_DO_LINK, '<div class="text-right"><a')],
    "td_fora_de_tr": [("<tr>", ""), ("</tr>", "")],
}
PARAMETROS_INVALIDAS = [pytest.param(trocas, id=nome) for nome, trocas in LINHAS_INVALIDAS.items()]


def _trocar(texto: str, trocas: list[tuple[str, str]]) -> str:
    """Aplica as trocas, exigindo que cada trecho exista uma única vez."""
    for antigo, novo in trocas:
        assert texto.count(antigo) == 1, f"trecho ausente ou repetido: {antigo!r}"
        texto = texto.replace(antigo, novo)
    return texto


def _pagina() -> str:
    return load_sample("tjpe", "cjsg/step_02_escolha.html")


def _linha_acordaos() -> str:
    pagina = _pagina()
    sem_linha = "a captura deixou de ter linha delimitada por <tr> sem atributo"
    assert "<tr>" in pagina, sem_linha
    assert "</tr>" in pagina, sem_linha
    inicio = pagina.index("<tr>")
    linha = pagina[inicio:pagina.index("</tr>", inicio) + len("</tr>")]
    assert ROTULO in linha, f"a primeira linha da captura não traz o rótulo no formato esperado: {ROTULO!r}"
    return linha


def _linha_alterada(trocas: list[tuple[str, str]]) -> str:
    return _trocar(_linha_acordaos(), trocas)


def _pagina_com(linhas: str) -> str:
    """Página capturada com a linha de acórdãos substituída por ``linhas``."""
    return _trocar(_pagina(), [(_linha_acordaos(), linhas)])


def _linha_copia() -> str:
    """Segunda linha de acórdãos, válida, com outro identificador."""
    return _linha_alterada([(PAR, f"{{'{ID_COPIA}':'{ID_COPIA}'}}")])


@pytest.mark.parametrize(
    ("tipo", "esperado"),
    [("Acórdãos", ID_ACORDAOS), ("Decisões Monocráticas", ID_MONOCRATICAS)],
)
def test_escolha_pagina_capturada(tipo, esperado):
    assert extract_escolha_button_id(_pagina(), tipo) == esperado


def test_escolha_tipo_padrao():
    assert extract_escolha_button_id(_pagina()) == ID_ACORDAOS


@pytest.mark.parametrize(
    "tipo",
    ["acórdãos", "Acórdãos ", "Acórdão", "Acordaos", "Decisões", "Monocráticas", "Sentenças"],
)
def test_escolha_exige_rotulo_exato(tipo):
    mensagem = f"Could not find escolha button for '{tipo}'"
    with pytest.raises(ValueError, match=f"^{re.escape(mensagem)}$"):
        extract_escolha_button_id(_pagina(), tipo)


@pytest.mark.parametrize("trocas", PARAMETROS_INVALIDAS)
def test_escolha_linha_invalida_nao_serve(trocas):
    html = _pagina_com(_linha_alterada(trocas))
    with pytest.raises(ValueError, match="Could not find escolha button for 'Acórdãos'"):
        extract_escolha_button_id(html)


@pytest.mark.parametrize("trocas", PARAMETROS_INVALIDAS)
def test_escolha_pula_linha_invalida_e_segue(trocas):
    html = _pagina_com(_linha_alterada(trocas) + _linha_copia())
    assert extract_escolha_button_id(html) == ID_COPIA


def test_escolha_pula_todas_as_invalidas_antes_da_valida():
    invalidas = "".join(_linha_alterada(trocas) for trocas in LINHAS_INVALIDAS.values())
    html = _pagina_com(invalidas + _linha_copia())
    assert extract_escolha_button_id(html) == ID_COPIA


def test_escolha_primeira_linha_valida_vence():
    html = _pagina_com(_linha_acordaos() + _linha_copia())
    assert extract_escolha_button_id(html) == ID_ACORDAOS


@pytest.mark.parametrize(
    ("trocas", "esperado"),
    [
        pytest.param(
            [(TEXTO, "953 <span>documentos</span> encontrados")], ID_ACORDAOS, id="texto_partido_por_tag"
        ),
        pytest.param(
            [(ROTULO, "<label>\nAc&oacute;rd&atilde;os&nbsp;</label>")], ID_ACORDAOS, id="rotulo_com_nbsp"
        ),
        pytest.param(
            [(CELULA_DO_LINK, '<td class="text-right"><span><a')], ID_ACORDAOS, id="link_dentro_de_span_na_celula"
        ),
        pytest.param(
            [(ROTULO, "<label>\nAc&oacute;rd&atilde;os \n</label>")],
            ID_ACORDAOS,
            id="rotulo_com_espaco_dos_dois_lados",
        ),
        pytest.param(
            [(CELULA_DO_LINK, f"<td></td>{CELULA_DO_LINK}")],
            ID_ACORDAOS,
            id="celula_extra_antes_do_link",
        ),
        pytest.param([(PAR, PAR.strip("{}"))], ID_ACORDAOS, id="par_sem_chaves"),
        pytest.param(
            [(PAR, "{'resultadoForm:primeiro':'valor','resultadoForm:segundo':'outro'}")],
            "resultadoForm:primeiro",
            id="chave_do_primeiro_par",
        ),
    ],
)
def test_escolha_variacoes_validas(trocas, esperado):
    assert extract_escolha_button_id(_pagina_com(_linha_alterada(trocas))) == esperado


def test_escolha_tipo_vazio_aceita_linha_sem_label():
    html = _pagina_com(_linha_alterada(LINHAS_INVALIDAS["rotulo_sem_label"]))
    assert extract_escolha_button_id(html, "") == ID_ACORDAOS


# As versões derivadas de "link fora de td" e "td fora de tr" dependem de a
# captura não ter tabela em volta da de escolha; estas não dependem de nada.
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
