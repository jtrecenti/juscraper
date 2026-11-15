"""Auto-chunk do cjsg eSAJ contra a regra real de janela do servidor.

O eSAJ aceita ``dtJulgamentoFim`` estritamente anterior a
``dtJulgamentoInicio`` + 1 ano de calendário. Probe ao vivo no TJAC
(2026-10, assunto 10069, órgão 0-3):

* ``01/01/2013``–``31/12/2013``: 200, 12 acórdãos;
* ``01/03/2015``–``29/02/2016``: 200 (365 dias de diferença, com 29/02);
* ``01/01/2013``–``01/01/2014``: 404 em ``trocaDePagina.do?pagina=1``
  (365 dias de diferença, sem 29/02).

O limite em dias fixos (366) gerava janelas que o servidor sempre recusa:
cada janela cheia virava ``UserWarning`` e só a última, mais curta,
chegava ao DataFrame. O servidor falso abaixo aplica a mesma regra e
responde cada janela aceita com a captura real ``single_page.html``,
renumerando ``cdAcordao`` por janela para que a deduplicação não esconda
janela perdida.
"""

import re
import warnings
from datetime import date
from urllib.parse import parse_qs

import pytest
import responses

import juscraper as jus
from juscraper.core.exceptions import ColetaParcialError
from tests._helpers import load_sample_bytes

ESAJ_PUROS = ["tjac", "tjal", "tjam", "tjce", "tjms"]
# TJSP usa o mesmo fluxo de POST + trocaDePagina no cjsg, sem ``data_publicacao``.
ESAJ_CJSG = [*ESAJ_PUROS, "tjsp"]
_CD_ACORDAO = re.compile(rb'cdAcordao="(\d+)"')
_CNJ_CJPG = re.compile(rb'(fonteNegrito">\s*[\d.-]+)')


def _data(texto: str) -> date:
    dia, mes, ano = (int(parte) for parte in texto.split("/"))
    return date(ano, mes, dia)


def _mais_um_ano(data: date) -> date:
    try:
        return data.replace(year=data.year + 1)
    except ValueError:  # 29/02 em ano não bissexto
        return data.replace(year=data.year + 1, day=28)


def _registrar_servidor_esaj(base_url: str, tribunal: str, fora_do_ar: str | None = None) -> list[tuple[str, str]]:
    """Registra POST + GET da 1a página com a regra de janela do eSAJ.

    ``fora_do_ar`` é o início de uma janela que responde 404 mesmo dentro da
    regra, para simular falha do servidor no meio da coleta. Devolve a lista,
    preenchida a cada POST, das janelas pedidas.
    """
    amostra = load_sample_bytes(tribunal, "cjsg/single_page.html")
    janelas: list[tuple[str, str]] = []

    def _post(request):
        corpo = parse_qs(request.body if isinstance(request.body, str) else request.body.decode())
        janelas.append((corpo["dados.dtJulgamentoInicio"][0], corpo["dados.dtJulgamentoFim"][0]))
        return 200, {}, b"<html></html>"

    def _primeira_pagina(_request):
        inicio, fim = (_data(d) for d in janelas[-1])
        if fim >= _mais_um_ano(inicio) or janelas[-1][0] == fora_do_ar:
            return 404, {}, b""
        prefixo = str(len(janelas)).encode()
        corpo = _CD_ACORDAO.sub(lambda m: b'cdAcordao="' + prefixo + b"0" + m.group(1) + b'"', amostra)
        return 200, {"Content-Type": "text/html; charset=latin-1"}, corpo

    responses.add_callback(responses.POST, f"{base_url}cjsg/resultadoCompleta.do", callback=_post)
    responses.add_callback(responses.GET, f"{base_url}cjsg/trocaDePagina.do", callback=_primeira_pagina)
    return janelas


def _acordaos_por_janela(tribunal: str) -> int:
    amostra = load_sample_bytes(tribunal, "cjsg/single_page.html")
    return len(set(_CD_ACORDAO.findall(amostra)))


@pytest.mark.parametrize("tribunal", ESAJ_CJSG)
@pytest.mark.parametrize(
    "caso",
    [
        ("01/01/2010", "31/12/2016", 7),  # Santos et al. (2022): 7 anos, com 2012 e 2016 bissextos
        ("01/01/2013", "31/12/2014", 2),
        ("01/01/2013", "01/01/2014", 2),  # 365 dias sem 29/02: o servidor recusa numa janela só
    ],
)
@responses.activate
def test_cjsg_auto_chunk_concatena_todas_as_janelas(tribunal, caso, tmp_path, mocker):
    """Toda janela gerada pelo auto-chunk é aceita pelo servidor e entra no resultado."""
    inicio, fim, n_janelas = caso
    mocker.patch("time.sleep")
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    janelas = _registrar_servidor_esaj(scraper.BASE_URL, tribunal)

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        df = scraper.cjsg("dano moral", data_julgamento_inicio=inicio, data_julgamento_fim=fim)

    assert len(janelas) == n_janelas
    assert janelas[0][0] == inicio
    assert janelas[-1][1] == fim
    assert len(df) == n_janelas * _acordaos_por_janela(tribunal)
    assert df["cd_acordao"].str[0].nunique() == n_janelas


@pytest.mark.parametrize("tribunal", ESAJ_CJSG)
@responses.activate
def test_cjsg_count_only_soma_todas_as_janelas(tribunal, tmp_path, mocker):
    """A contagem multi-janela usa as mesmas janelas aceitas pelo servidor."""
    mocker.patch("time.sleep")
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    janelas = _registrar_servidor_esaj(scraper.BASE_URL, tribunal)
    um_ano = scraper.cjsg(
        "dano moral", data_julgamento_inicio="01/01/2013", data_julgamento_fim="31/12/2013", count_only=True
    )

    total = scraper.cjsg(
        "dano moral", data_julgamento_inicio="01/01/2010", data_julgamento_fim="31/12/2016", count_only=True
    )

    assert len(janelas) == 1 + 7
    assert total == 7 * um_ano


@pytest.mark.parametrize("tribunal", ESAJ_CJSG)
@responses.activate
def test_cjsg_auto_chunk_janela_que_falha_levanta_com_o_parcial(tribunal, tmp_path, mocker):
    """Janela que falha não some calada: o erro nomeia a janela e carrega as que passaram."""
    mocker.patch("time.sleep")
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    _registrar_servidor_esaj(scraper.BASE_URL, tribunal, fora_do_ar="01/01/2013")

    with pytest.raises(ColetaParcialError, match="1 de 7 janela") as exc_info:
        scraper.cjsg("dano moral", data_julgamento_inicio="01/01/2010", data_julgamento_fim="31/12/2016")

    erro = exc_info.value
    assert [(i, f) for i, f, _ in erro.falhas] == [("01/01/2013", "31/12/2013")]
    assert len(erro.resultado) == 6 * _acordaos_por_janela(tribunal)


@pytest.mark.parametrize("tribunal", ESAJ_PUROS)
@pytest.mark.parametrize(
    "filtros",
    [
        {"data_julgamento_inicio": "01/01/2013", "data_julgamento_fim": "01/01/2014", "auto_chunk": False},
        {"data_publicacao_inicio": "01/01/2013", "data_publicacao_fim": "01/01/2014"},
    ],
    ids=["julgamento_sem_auto_chunk", "publicacao"],
)
@pytest.mark.parametrize("count_only", [False, True])
@responses.activate
def test_cjsg_intervalo_no_aniversario_trava_antes_da_requisicao(tribunal, filtros, count_only, tmp_path):
    """Sem auto-chunk, o intervalo que o servidor recusaria vira ValueError sem nenhuma requisição."""
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    janelas = _registrar_servidor_esaj(scraper.BASE_URL, tribunal)

    with pytest.raises(ValueError, match="no máximo 1 ano"):
        scraper.cjsg("", count_only=count_only, **filtros)

    assert janelas == []


@pytest.mark.parametrize("tribunal", ESAJ_PUROS)
@responses.activate
def test_cjsg_publicacao_longa_com_julgamento_longo_trava_antes_das_janelas(tribunal, tmp_path):
    """Publicação não é dividida: o ValueError sai antes do auto-chunk, sem virar falha de janela."""
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    janelas = _registrar_servidor_esaj(scraper.BASE_URL, tribunal)

    with pytest.raises(ValueError, match="no máximo 1 ano") as exc_info:
        scraper.cjsg(
            "dano moral",
            data_julgamento_inicio="01/01/2010",
            data_julgamento_fim="31/12/2016",
            data_publicacao_inicio="01/01/2013",
            data_publicacao_fim="01/01/2014",
        )

    assert not isinstance(exc_info.value, ColetaParcialError)
    assert janelas == []


def _registrar_servidor_cjpg(fora_do_ar: str | None = None) -> list[tuple[str, str]]:
    """GET ``cjpg/pesquisar.do`` do TJSP com a mesma regra de janela do eSAJ.

    A captura ``results_normal_page_01.html`` tem 10 decisões, e o total é
    trocado para 10 para caber numa página. O sufixo ``-j<n>`` no número do
    processo torna ``id_processo`` único por janela.
    """
    amostra = load_sample_bytes("tjsp", "cjpg/results_normal_page_01.html").replace(b"de 3565472", b"de 10")
    janelas: list[tuple[str, str]] = []

    def _pesquisar(request):
        janelas.append((request.params["dadosConsulta.dtInicio"], request.params["dadosConsulta.dtFim"]))
        inicio, fim = (_data(d) for d in janelas[-1])
        if fim >= _mais_um_ano(inicio) or janelas[-1][0] == fora_do_ar:
            return 404, {}, b""
        sufixo = f"-j{len(janelas)}".encode()
        return 200, {"Content-Type": "text/html; charset=utf-8"}, _CNJ_CJPG.sub(lambda m: m.group(1) + sufixo, amostra)

    responses.add_callback(responses.GET, "https://esaj.tjsp.jus.br/cjpg/pesquisar.do", callback=_pesquisar)
    return janelas


@pytest.mark.parametrize(("fora_do_ar", "n_ok"), [(None, 7), ("01/01/2013", 6)], ids=["todas", "uma_fora"])
@responses.activate
def test_cjpg_tjsp_auto_chunk_janelas_de_calendario(fora_do_ar, n_ok, tmp_path, mocker):
    """O cjpg do TJSP usa as mesmas janelas e o mesmo erro com parcial que o cjsg."""
    mocker.patch("time.sleep")
    janelas = _registrar_servidor_cjpg(fora_do_ar)
    scraper = jus.scraper("tjsp", download_path=str(tmp_path))

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        if fora_do_ar is None:
            df = scraper.cjpg("dano moral", data_julgamento_inicio="01/01/2010", data_julgamento_fim="31/12/2016")
        else:
            with pytest.raises(ColetaParcialError, match="1 de 7 janela") as exc_info:
                scraper.cjpg("dano moral", data_julgamento_inicio="01/01/2010", data_julgamento_fim="31/12/2016")
            df = exc_info.value.resultado

    assert janelas == [(f"01/01/{ano}", f"31/12/{ano}") for ano in range(2010, 2017)]
    assert len(df) == n_ok * 10
    assert df["id_processo"].nunique() == n_ok * 10


@pytest.mark.parametrize("tribunal", ESAJ_PUROS)
@responses.activate
def test_cjsg_count_only_diz_qual_janela_falhou(tribunal, tmp_path, mocker):
    """count_only para na primeira falha, e o erro diz que datas repetir."""
    mocker.patch("time.sleep")
    scraper = jus.scraper(tribunal, download_path=str(tmp_path))
    _registrar_servidor_esaj(scraper.BASE_URL, tribunal, fora_do_ar="01/01/2013")

    with pytest.raises(Exception) as exc_info:  # noqa: PT011 - o tipo é o do HTTP; o que importa é a nota
        scraper.cjsg(
            "dano moral", data_julgamento_inicio="01/01/2010", data_julgamento_fim="31/12/2016", count_only=True
        )

    assert "count_only: falhou a janela de 01/01/2013 a 31/12/2013." in exc_info.value.__notes__
