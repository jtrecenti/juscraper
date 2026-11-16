"""Unit tests for the TJSC result-item parser.

Most tests characterize behavior kept from the original parser. The tests on
the ``/TJSC`` suffix, on ``DECISÃO`` and on the class read from the ``<span>``
lock fixes: they fail against the parser that predates them.
"""
import datetime

import pytest
from bs4 import BeautifulSoup

from juscraper.courts.tjsc.parse import _parse_result_item, cjsg_parse_manager
from tests._helpers import load_sample


def _sample_items() -> dict[str, object]:
    soup = BeautifulSoup(
        load_sample("tjsc", "cjsg/result_item_variants.html"),
        "html.parser",
    )
    return {item["id"]: item for item in soup.find_all("div", class_="resultadoItem")}


def test_parse_result_item_strips_tjsc_suffix_and_keeps_later_decision():
    """The ``/TJSC`` suffix is dropped and a later DECISÃO stays next to EMENTA."""
    result = _parse_result_item(_sample_items()["direct-labels"])

    assert result == {
        "processo": "5001234-56.2024.8.24.0000",
        "classe": "Agravo de Instrumento",
        "orgao_julgador": "Primeira Câmara",
        "relator": "Desembargadora Ana",
        "ementa": "Ementa preferencial",
        "decisao": "Decisão posterior",
    }


def test_parse_result_item_fills_ementa_from_decisao_and_keeps_both():
    """DECISÃO fills a missing ementa and stays as its own field.

    Unaccented label variants map directly and unknown labels are ignored.
    """
    result = _parse_result_item(_sample_items()["normalized-labels"])

    assert result == {
        "orgao_julgador": "Segunda Câmara",
        "data_publicacao": "02/07/2025",
        "ementa": "Decisão usada como ementa",
        "decisao": "Decisão usada como ementa",
    }


def test_parse_result_item_keeps_decision_when_it_precedes_explicit_summary():
    """DECISÃO remains available when a later EMENTA takes precedence."""
    result = _parse_result_item(_sample_items()["decision-before-summary"])

    assert result == {
        "decisao": "Decisão preservada",
        "ementa": "Ementa preferencial",
    }


def test_parse_result_item_preserves_partial_matching():
    """Known labels embedded in longer text keep the first matching field."""
    result = _parse_result_item(_sample_items()["partial-labels"])

    assert result == {
        "relator": "Desembargador Bruno",
        "data_julgamento": "01/07/2025",
    }


def test_parse_result_item_preserves_zip_truncation():
    """A label without a corresponding value is ignored by pair truncation."""
    result = _parse_result_item(_sample_items()["truncated-pairs"])

    assert result == {"uf": "SC"}


def test_cjsg_parse_manager_drops_items_without_ementa_or_processo():
    """Items with neither ``ementa`` nor ``processo`` do not become rows.

    ``partial-labels`` and ``truncated-pairs`` are dropped; the other three stay.
    """
    with pytest.warns(UserWarning, match="2 registro"):
        df = cjsg_parse_manager([load_sample("tjsc", "cjsg/result_item_variants.html")])

    assert len(_sample_items()) == 5
    assert len(df) == 3
    assert df[["processo", "ementa"]].notna().any(axis=1).all()


def test_cjsg_parse_manager_reads_process_number_without_link():
    """Registro sem link ``a.numero-processo`` traz o número como texto (#495).

    Sample real: acórdão do Conselho da Magistratura, julgado em 09/07/2027
    segundo o portal, que mostra ``0000.14.36.787202-3/TJSC`` sem link.
    """
    df = cjsg_parse_manager([load_sample("tjsc", "cjsg/processo_sem_link.html", encoding="latin-1")])

    assert df["processo"].tolist() == ["0000.14.36.787202-3"]
    assert df["data_julgamento"].tolist() == [datetime.date(2027, 7, 9)]


def test_cjsg_parse_manager_drops_sc_suffix_from_linked_process_number():
    """O link traz ``<número>/SC`` além de ``<número>/TJSC``; nenhum sufixo fica em ``processo``.

    Sample real (16/11/2026): ``0000.20.06.300854-0/SC`` e
    ``0000.20.06.047047-0/TJSC`` na mesma página, os dois com link.
    """
    df = cjsg_parse_manager([load_sample("tjsc", "cjsg/processo_sufixo_sc.html", encoding="latin-1")])

    assert len(df) == 10
    assert {"0000.20.06.300854-0", "0000.20.06.047047-0"} <= set(df["processo"])
    assert not df["processo"].str.contains("/").any()


def test_cjsg_parse_manager_warns_when_process_number_is_missing():
    """Sem link nem texto ``/TJSC``, a linha fica sem processo e há aviso."""
    html = """
    <div class="resultadoItem">
      <div class="resLabel">PROCESSO</div>
      <div class="resValue"><span>422070 - Recurso Administrativo</span></div>
      <div class="resLabel">EMENTA</div>
      <div class="resValue">Ementa sem número</div>
    </div>
    """

    with pytest.warns(UserWarning, match="1 registro\\(s\\) sem número de processo"):
        df = cjsg_parse_manager([html])

    assert df["ementa"].tolist() == ["Ementa sem número"]
    assert "processo" not in df.columns


@pytest.mark.parametrize(
    ("sample", "classes"),
    [
        # Código numérico no lugar da sigla (Conselho da Magistratura), sem link no número.
        ("processo_sem_link.html", ["Recurso Administrativo"]),
        # Sigla em caixa mista (ApCiv) ao lado de sigla em maiúsculas (RCIJEF).
        ("results_normal_page_01.html", ["RECURSO CÍVEL"] + ["Apelação"] * 7 + ["RECURSO CÍVEL"] * 2),
        # Outra sigla em caixa mista (AgExPe), com RSE e AI.
        (
            "filtro_data_julgamento.html",
            ["RECURSO EM SENTIDO ESTRITO", "Agravo de Execução Penal", "Apelação"]
            + ["Agravo de Instrumento"] * 4
            + ["Apelação"] * 3,
        ),
        # Sigla com espaço (``HC TR``), que a leitura pela forma da linha perdia.
        (
            "classe_sigla_com_espaco.html",
            ["Agravo de Execução Penal", "Apelação Criminal", "Habeas Corpus Criminal", "Habeas Corpus Criminal TR"]
            + ["Habeas Corpus Criminal"] * 5
            + ["Agravo de Execução Penal"],
        ),
    ],
)
def test_cjsg_parse_manager_reads_class_from_span_of_second_column(sample, classes):
    """A classe vem do ``<span>`` da segunda coluna do campo PROCESSO, nos layouts dos samples reais."""
    df = cjsg_parse_manager([load_sample("tjsc", f"cjsg/{sample}", encoding="latin-1")])

    assert df["classe"].tolist() == classes


def test_parse_result_item_keeps_span_text_without_separator():
    """Sem `` - `` no ``<span>``, a classe é o texto inteiro dele."""
    html = """
    <div class="resultadoItem">
      <div class="resLabel">PROCESSO</div>
      <div class="resValue">
        <div class="row">
          <div class="col-12 col-md-auto"><a class="numero-processo">5000000-00.2024.8.24.0000/TJSC</a></div>
          <div class="col-12 col-md-auto"><span>Apelação</span></div>
        </div>
      </div>
    </div>
    """
    item = BeautifulSoup(html, "html.parser").find("div", class_="resultadoItem")

    assert _parse_result_item(item)["classe"] == "Apelação"


def test_cjsg_parse_manager_warns_when_class_span_is_missing():
    """Registro com processo e sem o ``<span>`` da classe fica sem classe, com aviso."""
    html = load_sample("tjsc", "cjsg/processo_sem_link.html", encoding="latin-1")
    span = "<span>422070 - Recurso Administrativo</span>"
    assert html.count(span) == 1

    with pytest.warns(UserWarning, match=r"1 registro\(s\) sem classe"):
        df = cjsg_parse_manager([html.replace(span, "")])

    assert df["processo"].tolist() == ["0000.14.36.787202-3"]
    assert "classe" not in df.columns
