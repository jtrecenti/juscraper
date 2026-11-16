"""Contratos dos timeouts que os raspadores passam ao core HTTP."""

import importlib

import pytest
import requests

from juscraper.courts.tjes.client import TJESScraper
from juscraper.courts.tjes.download import cjsg_download
from juscraper.courts.tjpe.client import TJPEScraper
from juscraper.courts.tjpr.client import TJPRScraper
from tests._helpers import load_sample_bytes


@pytest.mark.parametrize(
    ("modulo", "classe", "perfil", "timeout"),
    [
        ('courts.stf', 'STFScraper', 'cjsg', 60),
        ('courts.tjap', 'TJAPScraper', 'cjsg', 30),
        ('courts.tjba', 'TJBAScraper', 'cjsg', 60),
        ('courts.tjdft', 'TJDFTScraper', 'cjsg', 10),
        ('courts.tjes', 'TJESScraper', 'cjsg', 30),
        ('courts.tjgo', 'TJGOScraper', 'cjsg', 90),
        ('courts.tjgo', 'TJGOScraper', 'formulario', 60),
        ('courts.tjmt', 'TJMTScraper', 'configuracao', 30),
        ('courts.tjmt', 'TJMTScraper', 'busca', 60),
        ('courts.tjpa', 'TJPAScraper', 'cjsg', 30),
        ('courts.tjpb', 'TJPBScraper', 'classes', 30),
        ('courts.tjpb', 'TJPBScraper', 'cjsg', 30),
        ('courts.tjpe', 'TJPEScraper', 'cjsg', 30),
        ('courts.tjpe', 'TJPEScraper', 'cpopg', 30),
        ('courts.tjpi', 'TJPIScraper', 'cjsg', 30),
        ('courts.tjpr', 'TJPRScraper', 'cjsg', 60),
        ('courts.tjpr', 'TJPRScraper', 'ementa', 30),
        ('courts.tjrj', 'TJRJScraper', 'formulario', 30),
        ('courts.tjrj', 'TJRJScraper', 'cjsg', 60),
        ('courts.tjrn', 'TJRNScraper', 'cjsg', 30),
        ('courts.tjro', 'TJROScraper', 'cjsg', 30),
        ('courts.tjrr', 'TJRRScraper', 'formulario', 30),
        ('courts.tjrr', 'TJRRScraper', 'cjsg', 60),
        ('courts.tjsc', 'TJSCScraper', 'cjsg', 60),
        ('courts.tjto', 'TJTOScraper', 'ementa', 30),
        ('courts.tjto', 'TJTOScraper', 'cjsg', 60),
        ('aggregators.comunica_cnj', 'ComunicaCNJScraper', 'listagem', 30.0),
        ('aggregators.falcao', 'FalcaoScraper', 'listagem', 30.0),
        ('courts.trf1', 'TRF1Scraper', 'cpopg', 30),
        ('courts.trf5', 'TRF5Scraper', 'cpopg', 30),
        ('courts.tjac', 'TJACScraper', 'cjsg', 30),
        ('courts.tjac', 'TJACScraper', 'documento', 60),
        ('courts.tjac', 'TJACScraper', 'arvore', 60),
    ],
)
def test_timeout_esta_no_perfil_ajustavel(modulo, classe, perfil, timeout):
    scraper_cls = getattr(importlib.import_module(f"juscraper.{modulo}.client"), classe)
    scraper = scraper_cls(politica={perfil: {"timeout": 7}})
    assert scraper_cls.perfis_http[perfil].timeout == timeout
    # O dicionário privado é o resultado efetivo do ajuste no construtor.
    assert scraper._perfis_http[perfil].timeout == 7  # noqa: SLF001


def test_json_obrigatorio_esta_nos_perfis_de_busca():
    for modulo, classe, perfil in (
        ("courts.tjes", "TJESScraper", "cjsg"),
        ("courts.tjmt", "TJMTScraper", "busca"),
        ("aggregators.falcao", "FalcaoScraper", "listagem"),
    ):
        scraper_cls = getattr(importlib.import_module(f"juscraper.{modulo}.client"), classe)
        assert scraper_cls.perfis_http[perfil].expect_json is True


def test_tjes_requisicao_usa_timeout_ajustado(mocker):
    scraper = TJESScraper(politica={"cjsg": {"timeout": 7}})
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"docs": [], "total_pages": 1}'  # noqa: SLF001  # resposta sintetica de transporte
    response.headers["Content-Type"] = "application/json"
    request = mocker.patch.object(scraper.session, "request", return_value=response)

    # O downloader recebe o método HTTP efetivo do scraper.
    request_fn = scraper._request_with_retry  # noqa: SLF001
    assert cjsg_download("teste", paginas=[1], request_fn=request_fn) == [response.json()]
    assert request.call_args.kwargs["timeout"] == 7


def test_tjpe_repassa_politica_ao_cliente_cpopg(mocker):
    scraper = TJPEScraper(politica={"cpopg": {"timeout": 7}})
    consulta = scraper._consulta()  # noqa: SLF001  # cliente delegado do metodo publico
    response = requests.Response()
    response.status_code = 200
    request = mocker.patch.object(consulta.session, "request", return_value=response)

    consulta._request_with_retry("GET", "https://exemplo.test", perfil="cpopg")  # noqa: SLF001  # contrato HTTP
    assert request.call_args.kwargs["timeout"] == 7


def test_tjpr_requisicoes_usam_os_timeouts_ajustados(mocker):
    """Home e busca saem pelo perfil ``cjsg``; a ementa completa das linhas truncadas, pelo ``ementa``."""
    scraper = TJPRScraper(politica={"cjsg": {"timeout": 7}, "ementa": {"timeout": 5}})
    pagina, ementa = requests.Response(), requests.Response()
    pagina.status_code = ementa.status_code = 200
    pagina._content = load_sample_bytes("tjpr", "cjsg/results_normal_page_01.html")  # noqa: SLF001  # transporte
    ementa._content = b"Texto da ementa."  # noqa: SLF001  # resposta sintetica de transporte
    request = mocker.patch.object(scraper.session, "request", side_effect=lambda _metodo, url, **_: (
        ementa if "visualizarDecisao" in url else pagina
    ))

    brutos = scraper.cjsg_download("teste", paginas=1)
    assert [chamada.kwargs["timeout"] for chamada in request.call_args_list] == [7, 7]

    request.reset_mock()
    scraper.cjsg_parse(brutos)
    assert {chamada.kwargs["timeout"] for chamada in request.call_args_list} == {5}
