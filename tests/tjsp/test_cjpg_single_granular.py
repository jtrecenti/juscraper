"""Caracterização de ``cjpg_parse_single``.

Duas fontes, com papéis diferentes. As capturas ``results_normal_page_*.html``
fixam a saída do parser na página real, comparada com
``results_normal_expected.json``. Já :data:`_CAMPOS_OPCIONAIS` é montado à mão,
e não captura do tribunal, por isso fica neste arquivo e não em ``samples/``:
reúne os casos de borda que uma página real não traz juntos.

No primeiro resultado do HTML montado à mão, o bloco da decisão repete o
aninhamento da página real: uma ``tr.fonte`` sem rótulo, com o resumo visível
antes do ``div`` oculto que guarda o inteiro teor. O ``name`` do link tem
vários hifens e o texto da decisão tem tag colada em pontuação e quebra de
linha, como na captura. O link sem ``style`` que vem antes não existe na
página real: está ali para o teste depender do filtro de ``style``.
"""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from juscraper.courts._esaj.cjpg_parse import cjpg_parse_single

_TESTS = Path(__file__).parents[1]
_SAMPLES = _TESTS / "tjsp" / "samples" / "cjpg"

# Linha sem tabela, linha completa com rótulo inventado ("Tipo-de ato") e
# valor que repete o rótulo, linha sem identificadores e linha sem campos.
_CAMPOS_OPCIONAIS = """<div id="divDadosResultado">
  <tr class="fundocinza1"><td>Linha sem tabela</td></tr>
  <tr class="fundocinza1"><td><table>
    <a name="IGNORADO-0">Link sem estilo</a>
    <a style="vertical-align: top" name="CODIGO-126--sufixo"
      ><span class="fonteNegrito"> 1000000-00.2024.8.26.0001 </span></a>
    <tr class="fonte"><td><strong>Classe:</strong> Classe: complemento</td></tr>
    <tr class="fonte"><td><strong>Data de disponibilização:</strong> 01/02/2024</td></tr>
    <tr class="fonte"><td><strong>Tipo-de ato:</strong> Sentença</td></tr>
    <tr class="fonte"><td>Ignorar linha sem rótulo</td></tr>
    <tr class="fonte"><td>
      <div align="justify"><span>Resumo: trecho visível</span></div>
      <div align="justify" style="display: none;"><span>Resumo ignorado</span><span>Decisão <b>completa</b>.
Segunda linha.</span></div>
    </td></tr>
  </table></td></tr>
  <tr class="fundocinza1"><td><table>
    <a style="vertical-align: top">Sem identificadores</a>
    <div align="justify" style="display: none;">Sem spans</div>
  </table></td></tr>
  <tr class="fundocinza1"><td><table><tr><td>Sem campos opcionais</td></tr></table></td></tr>
</div>
"""


def _resumir(df):
    """Reduz a saída do parser à forma guardada em ``results_normal_expected.json``.

    As colunas curtas ficam por extenso. A decisão, que passa de dez mil
    caracteres, fica como SHA-256 e tamanho: qualquer mudança no texto aparece,
    sem um arquivo de referência do tamanho da própria captura. Para regerar o
    JSON depois de recapturar as páginas, gravar ``{nome: _resumir(...)}`` das
    duas capturas com ``ensure_ascii=False`` e ``indent=2``.
    """
    # Campo ausente vira ``None``: ``NaN`` não é igual a si mesmo depois da
    # ida e volta pelo JSON, e a comparação nunca passaria.
    linhas = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    for linha in linhas:
        texto = linha.get("decisao")
        if texto is not None:
            linha["decisao"] = {
                "sha256": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                "tamanho": len(texto),
            }
    return {"colunas": list(df.columns), "linhas": linhas}


@pytest.mark.parametrize("captura", ["results_normal_page_01.html", "results_normal_page_02.html"])
def test_capturas_reais_tem_saida_fixada(captura):
    """Fixa colunas, ordem e conteúdo do que o parser extrai da página real.

    O parser lê o arquivo da captura direto, sem a regravação que
    ``load_sample`` seguida de ``write_text`` faz, porque as capturas trazem
    CRLF dentro das decisões e a tradução de fim de linha faz parte do que se
    quer fixar.
    """
    esperado = json.loads((_SAMPLES / "results_normal_expected.json").read_text(encoding="utf-8"))[captura]
    obtido = _resumir(cjpg_parse_single(_SAMPLES / captura))

    assert obtido["colunas"] == esperado["colunas"]
    assert len(obtido["linhas"]) == len(esperado["linhas"])
    for posicao, (linha, referencia) in enumerate(zip(obtido["linhas"], esperado["linhas"], strict=True)):
        assert linha == referencia, f"linha {posicao}, processo {referencia['id_processo']}"


@pytest.mark.parametrize(
    ("tribunal", "captura"),
    [
        ("tjsp", "results_normal_page_01.html"),
        ("tjsp", "single_page.html"),
        ("tjms", "results_normal_page_01.html"),
    ],
)
def test_rotulo_magistrado_sai_na_coluna_relator(tribunal, captura):
    """O juiz, rotulado "Magistrado:" nas páginas do TJSP e do TJMS, sai em ``relator``.

    É o nome canônico do ``cjsg`` e dos demais tribunais, também no 1º grau.
    """
    df = cjpg_parse_single(_TESTS / tribunal / "samples" / "cjpg" / captura)

    assert "magistrado" not in df.columns
    assert df["relator"].notna().all()


def test_campos_opcionais_ordem_e_normalizacao(tmp_path):
    """Mantém linhas incompletas, ordem dos campos e o último span da decisão."""
    caminho = tmp_path / "resultados.html"
    caminho.write_text(_CAMPOS_OPCIONAIS, encoding="utf-8")

    resultado = cjpg_parse_single(caminho)

    esperado = pd.DataFrame([
        {
            "cd_processo": "CODIGO",
            "cd_foro": "126",
            "nm_alias": None,
            "cd_documento": "sufixo",
            "id_processo": "1000000-00.2024.8.26.0001",
            "classe": "Classe: complemento",
            "data_disponibilizacao": "01/02/2024",
            "tipode_ato": "Sentença",
            "decisao": "Decisão completa .\nSegunda linha.",
        },
        {
            "cd_processo": None,
            "cd_foro": None,
            "nm_alias": None,
            "cd_documento": None,
            "id_processo": None,
            "decisao": "",
        },
        {},
    ])
    pd.testing.assert_frame_equal(resultado, esperado)


@pytest.mark.parametrize("html", ["<html></html>", '<div id="divDadosResultado"></div>'])
def test_ausencia_de_resultados(tmp_path, html):
    caminho = tmp_path / "vazio.html"
    caminho.write_text(html, encoding="utf-8")
    pd.testing.assert_frame_equal(cjpg_parse_single(caminho), pd.DataFrame())


def test_rotulo_sem_separador_continua_rejeitado(tmp_path):
    """Fixa o comportamento atual, que não é validação deliberada.

    O ``ValueError`` nasce do desempacotamento de ``split(':', 1)`` e derruba a
    página inteira. Em modo diretório, ``cjpg_parse_manager`` captura o erro e
    descarta os resultados desse arquivo.
    """
    caminho = tmp_path / "invalido.html"
    caminho.write_text(
        '<div id="divDadosResultado"><tr class="fundocinza1"><table>'
        '<tr class="fonte"><td><strong>Classe sem separador</strong></td></tr>'
        '</table></tr></div>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not enough values to unpack"):
        cjpg_parse_single(caminho)
