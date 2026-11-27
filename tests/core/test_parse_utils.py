"""Testes de ``juscraper.core.parse_utils``."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from juscraper.core.parse_utils import (
    clean_document_text,
    clean_html,
    coerce_date_columns,
    html_para_texto,
    normalizar_colunas_texto,
    normalizar_texto,
)


class TestCleanHtml:
    def test_remove_tags(self):
        assert clean_html("<p>texto</p>") == "texto"

    def test_decode_named_entities(self):
        assert clean_html("&Aacute;gua &amp; fogo") == "Água & fogo"

    def test_decode_numeric_entities(self):
        assert clean_html("&#193;gua &#x41;") == "Água A"

    def test_no_entities_flag(self):
        assert clean_html("&amp; texto", decode_entities=False) == "&amp; texto"

    def test_no_entities_flag_with_tags(self):
        assert clean_html("<p>&amp; texto</p>", decode_entities=False) == "&amp; texto"

    def test_none_passthrough(self):
        assert clean_html(None) is None

    def test_empty_string_passthrough(self):
        assert clean_html("") == ""

    def test_collapse_whitespace(self):
        assert clean_html("<p>a\n\n  b</p>") == "a b"

    def test_combined_tags_and_entities(self):
        result = clean_html("<b>R$&nbsp;1.000</b>")
        assert result == "R$ 1.000"

    def test_decode_extended_named_entities(self):
        # html.unescape cobre toda a tabela HTML5 — não só o subset
        # acute/grave/etc do _clean_html original do TJAP.
        assert clean_html("&copy; 2024 &hellip; &deg;C") == "© 2024 … °C"

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            ("<b>DANOS</b>.", "DANOS."),
            ("(<i>ii</i>)", "(ii)"),
        ],
    )
    def test_tag_inline_some_sem_deixar_espaco(self, entrada, esperado):
        assert clean_html(entrada) == esperado

    def test_bloco_e_br_viram_espaco(self):
        assert clean_html("<p>Primeira</p><p>Segunda<br>Terceira</p>") == "Primeira Segunda Terceira"

    def test_remove_conteudo_de_style(self):
        assert clean_html("<style>p{text-align: justify;}</style><p>Ementa</p>") == "Ementa"

    def test_remove_comentario(self):
        assert clean_html("<!--[if gte mso 9]>Normal 0 21 false<![endif]-->Texto") == "Texto"

    def test_menor_que_solto_fica(self):
        assert clean_html("menor (<18 anos) e maior (>60 anos)") == "menor (<18 anos) e maior (>60 anos)"

    def test_sem_decodificar_ainda_normaliza(self):
        assert clean_html("a\xa0b&nbsp;c\u200b", decode_entities=False) == "a b&nbsp;c"


class TestCoerceDateColumns:
    def test_empty_df_no_raise(self):
        df = pd.DataFrame()
        out = coerce_date_columns(df, ["data_julgamento"])
        assert out.empty

    def test_iso_format(self):
        df = pd.DataFrame({"data_julgamento": ["2024-01-15", "2024-02-20"]})
        coerce_date_columns(df, ["data_julgamento"])
        assert df["data_julgamento"].tolist() == [dt.date(2024, 1, 15), dt.date(2024, 2, 20)]

    def test_none_to_nat(self):
        df = pd.DataFrame({"data_julgamento": [None, "2024-01-15"]})
        coerce_date_columns(df, ["data_julgamento"])
        assert pd.isna(df["data_julgamento"].iloc[0])
        assert df["data_julgamento"].iloc[1] == dt.date(2024, 1, 15)

    def test_missing_columns_silent_noop(self):
        df = pd.DataFrame({"foo": [1, 2]})
        out = coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
        assert list(out.columns) == ["foo"]
        assert out["foo"].tolist() == [1, 2]

    def test_returns_same_df(self):
        df = pd.DataFrame({"data_julgamento": ["2024-01-15"]})
        out = coerce_date_columns(df, ["data_julgamento"])
        assert out is df

    def test_multiple_columns(self):
        df = pd.DataFrame({
            "data_julgamento": ["2024-01-15"],
            "data_publicacao": ["2024-01-20"],
            "outra": ["x"],
        })
        coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
        assert df["data_julgamento"].iloc[0] == dt.date(2024, 1, 15)
        assert df["data_publicacao"].iloc[0] == dt.date(2024, 1, 20)
        assert df["outra"].iloc[0] == "x"

    def test_date_format_br(self):
        # Sem ``date_format``, ``03/02/2024`` poderia ser lido como
        # 2 de março (formato americano). Com ``%d/%m/%Y`` virou 3 de fevereiro.
        df = pd.DataFrame({"data_julgamento": ["03/02/2024", "15/01/2024"]})
        coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
        assert df["data_julgamento"].tolist() == [dt.date(2024, 2, 3), dt.date(2024, 1, 15)]

    def test_date_format_keyword_only(self):
        df = pd.DataFrame({"data_julgamento": ["03/02/2024"]})
        with pytest.raises(TypeError):
            coerce_date_columns(df, ["data_julgamento"], "%d/%m/%Y")  # type: ignore[call-arg]

    def test_date_format_invalid_for_content_returns_nat(self):
        # Conteúdo ISO não bate com ``%d/%m/%Y`` -> ``errors="coerce"`` vira NaT.
        df = pd.DataFrame({"data_julgamento": ["2024-01-15", "2024-02-20"]})
        coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
        assert df["data_julgamento"].isna().all()

    def test_date_format_none_default_preserves_iso(self):
        # ``date_format=None`` (default) mantém o caminho de inferência atual.
        df = pd.DataFrame({"data_julgamento": ["2024-01-15"]})
        coerce_date_columns(df, ["data_julgamento"], date_format=None)
        assert df["data_julgamento"].iloc[0] == dt.date(2024, 1, 15)

    def test_returns_same_df_with_date_format(self):
        df = pd.DataFrame({"data_julgamento": ["15/01/2024"]})
        out = coerce_date_columns(df, ["data_julgamento"], date_format="%d/%m/%Y")
        assert out is df


class TestNormalizarTexto:
    def test_fins_de_linha_viram_quebra(self):
        assert normalizar_texto("a\r\nb\rc\nd") == "a\nb\nc\nd"

    def test_espaco_nao_separavel_vira_espaco_comum(self):
        assert normalizar_texto("art.\xa014,\xa0do\xa0CDC") == "art. 14, do CDC"

    @pytest.mark.parametrize("invisivel", ["\xad", "\u200b", "\u200c", "\u200d"])
    def test_remove_invisiveis(self, invisivel):
        assert normalizar_texto(f"MANDADO{invisivel} {invisivel}DE") == "MANDADO DE"

    def test_preserva_espacos_tabs_e_paragrafos(self):
        texto = "  1.\tCinge-se  a\n\n controvérsia \n"
        assert normalizar_texto(texto) == texto

    @pytest.mark.parametrize("valor", [None, 1, 2.5, float("nan")], ids=["none", "int", "float", "nan"])
    def test_nao_str_volta_igual(self, valor):
        assert normalizar_texto(valor) is valor


class TestNormalizarColunasTexto:
    def test_normaliza_so_as_colunas_pedidas(self):
        df = pd.DataFrame({"ementa": ["a\xa0b\r\nc", None], "conteudo_html": ["<p>a\r\n</p>", "x\xa0y"]})
        out = normalizar_colunas_texto(df, ["ementa", "inexistente"])
        assert out is df
        assert df["ementa"].iloc[0] == "a b\nc"
        assert pd.isna(df["ementa"].iloc[1])
        assert df["conteudo_html"].tolist() == ["<p>a\r\n</p>", "x\xa0y"]


class TestHtmlParaTexto:
    def test_paragrafos_e_br_viram_quebra(self):
        html = "<p>EMENTA: RECURSO.</p><h3>I. CASO</h3><ol><li>Um.</li><li>Dois<br/>tres</li></ol>"
        assert html_para_texto(html) == "EMENTA: RECURSO.\nI. CASO\nUm.\nDois\ntres"

    def test_tag_inline_some_sem_espaco(self):
        assert html_para_texto("<p><b>DANO</b>, <font><b>MORAL</b></font>.</p>") == "DANO, MORAL."

    def test_quebra_do_codigo_fonte_vale_espaco(self):
        assert html_para_texto("<p>Caracteriza\n   do\r\n dano.</p>\n\n<p>Fim.</p>") == "Caracteriza do dano.\nFim."

    def test_preservar_quebras_mantem_o_fim_de_linha_do_texto(self):
        texto = "TITULO <em>DANO</em>\r\nI. Caso<br/>Trata-se\n\n  de recurso"
        assert html_para_texto(texto, preservar_quebras=True) == "TITULO DANO\nI. Caso\nTrata-se\nde recurso"

    def test_linhas_vazias_e_espacos_saem(self):
        html = "<p>&nbsp;</p><p>  a \t  b  </p><p><span>\xa0</span></p><div></div><p>c</p>"
        assert html_para_texto(html) == "a b\nc"

    def test_entidades_e_caracteres_invisiveis(self):
        html = "<p>art.&nbsp;14 &lt;CDC&gt; &amp; S&uacute;mula\u200b 7\xad</p>"
        assert html_para_texto(html) == "art. 14 <CDC> & Súmula 7"

    def test_remove_comentario_style_script_e_title(self):
        html = (
            "<html><head><title>Doc</title><style>p{text-align: justify;}</style></head>"
            "<body><!--[if gte mso 9]><xml>Normal 0 21 false</xml><![endif]-->"
            "<script>var x = 1;</script><p>Texto.</p></body></html>"
        )
        assert html_para_texto(html) == "Texto."

    @pytest.mark.parametrize(
        "html",
        ["<p>Texto.</p><style>p{x}", "<p>Texto.</p><!-- comentario", '<p>Texto.</p>   <p dir="ltr" s'],
        ids=["style", "comentario", "tag"],
    )
    def test_trecho_sem_fechamento_vai_ate_o_fim(self, html):
        assert html_para_texto(html) == "Texto."

    def test_celulas_separadas_por_espaco(self):
        assert html_para_texto("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td></tr></table>") == "a b\nc"

    @pytest.mark.parametrize("valor", [None, ""], ids=["none", "vazia"])
    def test_vazio_volta_igual(self, valor):
        assert html_para_texto(valor) is valor

    def test_html_sem_texto_vira_string_vazia(self):
        assert html_para_texto("<p>&nbsp;</p>") == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestCleanDocumentText:
    def test_remove_caracteres_de_controle_e_normaliza_quebras(self):
        txt = "abc\x00def\x1aghi\r\njkl\u2028mno\u2029pqr\rstu\xa0vwx"
        assert clean_document_text(txt) == "abcdefghi\njkl\nmno\npqr\nstu vwx"

    def test_apara_as_pontas(self):
        assert clean_document_text("  \n texto \r\n") == "texto"

    @pytest.mark.parametrize("vazio", [None, "", "   ", "\n\t ", "\xa0\r\n", "\x00"])
    def test_sem_texto_aproveitavel_devolve_none(self, vazio):
        assert clean_document_text(vazio) is None
