"""Caracterização de ``cjpg_parse_single``.

Duas fontes, com papéis diferentes. As capturas ``results_normal_page_*.html``
fixam a saída do parser na página real, comparada com
``results_normal_expected.json``. Já ``results_optional_fields.html`` é montado
à mão, e não captura do tribunal: reúne num arquivo só os casos de borda que
uma página real não traz juntos.

No primeiro resultado do arquivo montado à mão, o bloco da decisão repete o
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

from juscraper.courts.tjsp.cjpg_parse import cjpg_parse_single
from tests._helpers import load_sample

_SAMPLES = Path(__file__).parent / "samples" / "cjpg"


def _resumir(df):
    """Reduz a saída do parser à forma guardada em ``results_normal_expected.json``.

    As colunas curtas ficam por extenso. A decisão, que passa de dez mil
    caracteres, fica como SHA-256 e tamanho: qualquer mudança no texto aparece,
    sem um arquivo de referência do tamanho da própria captura. Para regerar o
    JSON depois de recapturar as páginas, gravar ``{nome: _resumir(...)}`` das
    duas capturas com ``ensure_ascii=False`` e ``indent=2``.
    """
    linhas = df.to_dict(orient="records")
    for linha in linhas:
        texto = linha["decisao"]
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
    referencia = json.loads((_SAMPLES / "results_normal_expected.json").read_text(encoding="utf-8"))

    assert _resumir(cjpg_parse_single(_SAMPLES / captura)) == referencia[captura]


def test_campos_opcionais_ordem_e_normalizacao(tmp_path):
    """Mantém linhas incompletas, ordem dos campos e o último span da decisão."""
    caminho = tmp_path / "resultados.html"
    caminho.write_text(load_sample("tjsp", "cjpg/results_optional_fields.html"), encoding="utf-8")

    resultado = cjpg_parse_single(caminho)

    esperado = pd.DataFrame([
        {
            "cd_processo": "CODIGO",
            "id_processo": "1000000-00.2024.8.26.0001",
            "classe": "Classe: complemento",
            "data_disponibilizacao": "01/02/2024",
            "tipode_ato": "Sentença",
            "decisao": "Decisão completa .\nSegunda linha.",
        },
        {"cd_processo": None, "id_processo": None, "decisao": ""},
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
