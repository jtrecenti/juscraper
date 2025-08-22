"""
Testes para validação de tamanho de query no TJSP (CJPG e CJSG).
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from src.juscraper.courts.tjsp.cjpg_download import cjpg_download, QueryTooLongError as CJPGQueryTooLongError
from src.juscraper.courts.tjsp.cjsg_download import cjsg_download, QueryTooLongError as CSJGQueryTooLongError


class TestCJPGQueryValidation:
    """Testes de validação de query para CJPG."""
    
    def test_valid_query_passes(self):
        """Query válida (≤120 chars) deve passar na validação de tamanho."""
        short_query = "direito civil"
        
        # A função deve falhar por outros motivos (session=None), não por tamanho da query
        with pytest.raises(AttributeError):  # Erro esperado por session=None
            cjpg_download(short_query, None, "", "", get_n_pags_callback=lambda x: 1)
    
    def test_query_exactly_120_chars_passes(self):
        """Query com exatamente 120 caracteres deve passar."""
        exact_query = "x" * 120
        
        # A função deve falhar por outros motivos, não por tamanho da query
        with pytest.raises(AttributeError):  # Erro esperado por session=None
            cjpg_download(exact_query, None, "", "", get_n_pags_callback=lambda x: 1)
    
    def test_query_over_120_chars_fails(self):
        """Query com mais de 120 caracteres deve ser rejeitada."""
        long_query = "x" * 121
        
        with pytest.raises(CJPGQueryTooLongError) as exc_info:
            cjpg_download(long_query, None, "", "", get_n_pags_callback=lambda x: 1)
        
        assert "120 caracteres suportado pela plataforma TJSP" in str(exc_info.value)
        assert "121 caracteres" in str(exc_info.value)
    
    def test_very_long_query_fails(self):
        """Query muito longa deve ser rejeitada com mensagem informativa."""
        very_long_query = "direito civil " * 20  # ~300 caracteres
        
        with pytest.raises(CJPGQueryTooLongError) as exc_info:
            cjpg_download(very_long_query, None, "", "", get_n_pags_callback=lambda x: 1)
        
        assert "120 caracteres suportado pela plataforma TJSP" in str(exc_info.value)
        assert f"{len(very_long_query)} caracteres" in str(exc_info.value)


class TestCJSGQueryValidation:
    """Testes de validação de query para CJSG."""
    
    def test_valid_query_passes(self):
        """Query válida (≤120 chars) deve passar na validação de tamanho."""
        short_query = "direito civil"
        
        # A função deve falhar por outros motivos (webdriver), não por tamanho da query
        with pytest.raises(Exception):  # Qualquer erro exceto QueryTooLongError
            try:
                cjsg_download(short_query, "", "", get_n_pags_callback=lambda x: 1)
            except CSJGQueryTooLongError:
                pytest.fail("Query válida foi rejeitada por tamanho")
    
    def test_query_exactly_120_chars_passes(self):
        """Query com exatamente 120 caracteres deve passar."""
        exact_query = "x" * 120
        
        # A função deve falhar por outros motivos, não por tamanho da query
        with pytest.raises(Exception):  # Qualquer erro exceto QueryTooLongError
            try:
                cjsg_download(exact_query, "", "", get_n_pags_callback=lambda x: 1)
            except CSJGQueryTooLongError:
                pytest.fail("Query de 120 chars foi rejeitada incorretamente")
    
    def test_query_over_120_chars_fails(self):
        """Query com mais de 120 caracteres deve ser rejeitada."""
        long_query = "x" * 121
        
        with pytest.raises(CSJGQueryTooLongError) as exc_info:
            cjsg_download(long_query, "", "", get_n_pags_callback=lambda x: 1)
        
        assert "120 caracteres suportado pela plataforma TJSP" in str(exc_info.value)
        assert "121 caracteres" in str(exc_info.value)
    
    def test_very_long_query_fails(self):
        """Query muito longa deve ser rejeitada com mensagem informativa."""
        very_long_query = "direito civil " * 20  # ~300 caracteres
        
        with pytest.raises(CSJGQueryTooLongError) as exc_info:
            cjsg_download(very_long_query, "", "", get_n_pags_callback=lambda x: 1)
        
        assert "120 caracteres suportado pela plataforma TJSP" in str(exc_info.value)
        assert f"{len(very_long_query)} caracteres" in str(exc_info.value)


class TestQueryErrorMessage:
    """Testes específicos para as mensagens de erro."""
    
    @pytest.mark.parametrize("query_length,module_name,error_class", [
        (121, "CJPG", CJPGQueryTooLongError),
        (150, "CJPG", CJPGQueryTooLongError), 
        (121, "CJSG", CSJGQueryTooLongError),
        (200, "CJSG", CSJGQueryTooLongError),
    ])
    def test_error_message_format(self, query_length, module_name, error_class):
        """Mensagem de erro deve ter formato consistente."""
        long_query = "x" * query_length
        
        if module_name == "CJPG":
            func = cjpg_download
            args = (long_query, None, "", "", )
            kwargs = {"get_n_pags_callback": lambda x: 1}
        else:
            func = cjsg_download
            args = (long_query, "", "")
            kwargs = {"get_n_pags_callback": lambda x: 1}
        
        with pytest.raises(error_class) as exc_info:
            func(*args, **kwargs)
        
        error_msg = str(exc_info.value)
        
        # Verificar elementos obrigatórios da mensagem
        assert "A consulta excede o limite de 120 caracteres suportado pela plataforma TJSP" in error_msg
        assert f"Query atual: {query_length} caracteres" in error_msg
        assert "Por favor, reduza o tamanho da consulta" in error_msg


if __name__ == "__main__":
    pytest.main([__file__, "-v"])