"""Cliente para o scraper do Conselho Nacional de Justiça (CNJ)."""

import shutil

from .download import cjpg_download
from .parse import cjpg_parse_manager


class ComunicaCNJ:
    """Raspador para o site de Comunicações Processuais do Conselho Nacional de Justiça."""

    def __init__(self):
        """Inicializa a classe."""
        self.api_base = 'https://comunicaapi.pje.jus.br/api/v1/comunicacao'

    def cjpg(
        self,
        pesquisa: str,
        data_inicio: str | None = None,
        data_fim: str | None = None,
        paginas: range | None = None,
    ):
        """
        Realiza uma busca por jurisprudencia com base nos parametros fornecidos.

        Baixa os resultados, os analisa e retorna os dados analisados.

        Args:
            pesquisa (str): A consulta para a jurisprudencia.
            data_inicio (str, opcional): A data de inicio para a busca. Padrao None.
            data_fim (str, opcional): A data de fim para a busca. Padrao None.
            paginas (range, opcional): A faixa de paginas a serem buscadas. Padrao None.

        Retorna:
            pd.DataFrame: Os dados analisados da jurisprudencia baixada.
        """
        path_result = cjpg_download(self.api_base, pesquisa, data_inicio, data_fim, paginas)
        data_parsed = cjpg_parse_manager(path_result)
        shutil.rmtree(path_result)
        return data_parsed
