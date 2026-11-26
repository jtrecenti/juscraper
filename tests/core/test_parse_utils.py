"""Testes de ``juscraper.core.parse_utils``."""
from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from juscraper.core.parse_utils import (
    clean_document_text,
    clean_html,
    coerce_date_columns,
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
            coerce_date_columns(df, ["data_julgamento"], "%d/%m/%Y")  # type: ignore[misc]

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
