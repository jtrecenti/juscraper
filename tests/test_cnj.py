"""Testes para utilitários de número CNJ."""
import pytest

from juscraper.utils.cnj import clean_cnj, format_cnj, split_cnj


class TestCleanCnj:
    def test_remove_dots_and_dashes(self):
        assert clean_cnj("0003325-88.2014.8.01.0001") == "00033258820148010001"

    def test_already_clean(self):
        assert clean_cnj("00033258820148010001") == "00033258820148010001"

    def test_strips_trailing_space(self):
        # Issue #59: CSVs exportados de Excel costumam trazer espaço sobrando.
        assert clean_cnj("00033258820148010001 ") == "00033258820148010001"

    def test_strips_leading_space(self):
        assert clean_cnj(" 00033258820148010001") == "00033258820148010001"

    def test_removes_newlines_and_tabs(self):
        assert clean_cnj("00033258820148010001\n") == "00033258820148010001"
        assert clean_cnj("\t00033258820148010001\t") == "00033258820148010001"

    def test_removes_internal_whitespace(self):
        assert clean_cnj("0003325 8820148010001") == "00033258820148010001"

    def test_formatted_with_trailing_space(self):
        assert clean_cnj("0003325-88.2014.8.01.0001\n") == "00033258820148010001"


class TestSplitCnj:
    def test_split_clean_number(self):
        partes = split_cnj("00033258820148010001")
        assert partes == {
            "num": "0003325",
            "dv": "88",
            "ano": "2014",
            "justica": "8",
            "tribunal": "01",
            "orgao": "0001",
        }

    def test_split_handles_whitespace(self):
        # Antes da correção #59 isso levantava ValueError silenciosamente
        # quando vindo de DataJud — agora funciona.
        assert split_cnj("00033258820148010001 ")["tribunal"] == "01"

    def test_split_invalid_length_raises(self):
        with pytest.raises(ValueError, match="20 dígitos"):
            split_cnj("123")


class TestFormatCnj:
    def test_format_from_clean(self):
        assert format_cnj("00033258820148010001") == "0003325-88.2014.8.01.0001"

    def test_format_idempotent(self):
        assert format_cnj("0003325-88.2014.8.01.0001") == "0003325-88.2014.8.01.0001"
