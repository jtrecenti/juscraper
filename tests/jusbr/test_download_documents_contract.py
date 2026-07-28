"""Offline contract tests for JusbrScraper.download_documents.

Fluxo real do ``download_documents`` (de ``aggregators/jusbr/client.py``):

1. Para cada linha em ``base_df``: extrai ``numeroProcesso``, ``detalhes``.
2. Caminha por ``detalhes['dadosBasicos']['documentos']`` (com fallbacks em
   ``detalhes['documentos']`` e ``detalhes['tramitacaoAtual']['documentos']``).
3. Para cada documento, extrai UUID de ``hrefTexto`` e ``hrefBinario``
   independentes. Followup 3 da #141: documento so e pulado quando **os
   dois** UUIDs faltam; com qualquer um valido, baixa o que da:
   - so ``hrefTexto`` -> linha com ``texto`` preenchido e
     ``_raw_binary_api == None``.
   - so ``hrefBinario`` -> linha com ``texto == None`` e
     ``_raw_binary_api`` preenchido.
4. URLs:
   - texto em ``api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/...``
   - binario em ``portaldeservicos.pdpj.jus.br/api/v2/...`` (NAO data-lake)
5. Linha de saida tem ``numero_processo``, ``texto``, ``_raw_text_api``,
   ``_raw_binary_api`` + todos os campos do ``doc_meta``.

Samples (``text_typical.txt`` / ``binary_typical.bin``) sao capturados via
``tests/fixtures/capture/jusbr.py``.
"""
from typing import Any

import jwt
import numpy as np
import pandas as pd
import pytest
import responses
from pydantic import ValidationError
from responses.registries import OrderedRegistry

import juscraper as jus
from tests._helpers import assert_unknown_kwarg_raises, load_sample, load_sample_bytes

BASE_TEXT_URL = "https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos"
BASE_BINARY_URL = "https://portaldeservicos.pdpj.jus.br/api/v2/processos"
HMAC_KEY = "0123456789abcdef0123456789abcdef-test"

CNJ_DIGITS = "00000000000000000000"
CNJ_DIGITS_2 = "11111111111111111111"
UUID_TEXT_1 = "11111111-1111-1111-1111-111111111111"
UUID_BIN_1 = "22222222-2222-2222-2222-222222222222"
UUID_TEXT_2 = "33333333-3333-3333-3333-333333333333"
UUID_BIN_2 = "44444444-4444-4444-4444-444444444444"
UUID_TEXT_3 = "55555555-5555-5555-5555-555555555555"
UUID_TEXT_4 = "66666666-6666-6666-6666-666666666666"


def _fake_jwt() -> str:
    encoded: str = jwt.encode({"sub": "tester", "exp": 9999999999}, HMAC_KEY, algorithm="HS256")
    return encoded


def _authenticated_scraper(sleep_time: float = 0.0):
    scraper = jus.scraper("jusbr", sleep_time=sleep_time)
    scraper.auth(_fake_jwt())
    return scraper


def _doc_meta(*, href_texto: str | None, href_binario: str | None, **extra) -> dict:
    """Build a documento metadata dict like the PDPJ ``dadosBasicos.documentos`` items."""
    meta = {
        "idDocumento": extra.get("idDocumento", "doc-id-1"),
        "sequencia": extra.get("sequencia", 1),
        "descricao": extra.get("descricao", "Peticao Inicial"),
        "tipo": extra.get("tipo", "PETICAO"),
    }
    if href_texto is not None:
        meta["hrefTexto"] = href_texto
    if href_binario is not None:
        meta["hrefBinario"] = href_binario
    meta.update({key: value for key, value in extra.items() if key not in meta})
    return meta


def _base_df(documentos: list[Any], numero_processo: str = CNJ_DIGITS) -> pd.DataFrame:
    """Build the input DataFrame for ``download_documents``."""
    return _base_df_with_details(
        {"dadosBasicos": {"documentos": documentos}},
        numero_processo=numero_processo,
    )


def _base_df_with_details(
    detalhes: dict[str, Any],
    numero_processo: str = CNJ_DIGITS,
) -> pd.DataFrame:
    """Build the input DataFrame with an explicit ``detalhes`` payload."""
    return pd.DataFrame([{
        "processo_pesquisado": numero_processo,
        "numeroProcesso": numero_processo,
        "processo": numero_processo,
        "idCodexTribunal": "TRIB",
        "detalhes": detalhes,
    }])


def _href_texto(uuid: str, numero_processo: str = CNJ_DIGITS) -> str:
    return f"/processos/{numero_processo}/documentos/{uuid}/texto"


def _href_binario(uuid: str, numero_processo: str = CNJ_DIGITS) -> str:
    return f"/processos/{numero_processo}/documentos/{uuid}/binario"


@responses.activate(registry=OrderedRegistry)
def test_download_documents_baixa_texto_e_binario(mocker):
    """``hrefTexto`` + ``hrefBinario`` -> texto + binario na linha de saida."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.columns[0] == "numero_processo"
    assert df.iloc[0]["numero_processo"] == CNJ_DIGITS
    assert isinstance(df.iloc[0]["texto"], str) and len(df.iloc[0]["texto"]) > 0
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)
    assert len(df.iloc[0]["_raw_binary_api"]) > 0


@responses.activate(registry=OrderedRegistry)
def test_download_documents_sem_href_binario_baixa_so_texto(mocker):
    """Sem ``hrefBinario``: linha com ``texto`` populado e ``_raw_binary_api == None``.

    Followup 3 da #141: download parcial em vez de skip.
    """
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=None),
    ])

    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert isinstance(df.iloc[0]["texto"], str) and len(df.iloc[0]["texto"]) > 0
    assert df.iloc[0]["_raw_binary_api"] is None


@responses.activate(registry=OrderedRegistry)
def test_download_documents_sem_href_texto_baixa_so_binario(mocker):
    """Sem ``hrefTexto``: linha com ``_raw_binary_api`` populado e ``texto == None``."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=None, href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["texto"] is None
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)
    assert len(df.iloc[0]["_raw_binary_api"]) > 0


@responses.activate(registry=OrderedRegistry)
def test_download_documents_href_texto_malformado_baixa_so_binario(mocker):
    """``hrefTexto`` sem ``/documentos/`` -> sem UUID de texto -> baixa so binario."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto="/path/sem/marcador", href_binario=_href_binario(UUID_BIN_1)),
    ])

    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["texto"] is None
    assert isinstance(df.iloc[0]["_raw_binary_api"], bytes)


@responses.activate(registry=OrderedRegistry)
def test_download_documents_ambos_hrefs_ausentes_pula_documento(mocker):
    """Sem ``hrefTexto`` nem ``hrefBinario`` -> documento pulado, sem HTTP."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(href_texto=None, href_binario=None),
    ])

    df = scraper.download_documents(base_df)
    # Nenhum responses.add — o teste tambem confirma que nenhum HTTP saiu.
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@responses.activate(registry=OrderedRegistry)
def test_download_documents_max_docs_per_process_limita(mocker):
    """``max_docs_per_process=1`` com 2 docs -> baixa apenas o primeiro."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()

    base_df = _base_df([
        _doc_meta(
            href_texto=_href_texto(UUID_TEXT_1),
            href_binario=_href_binario(UUID_BIN_1),
            idDocumento="doc-1",
            sequencia=1,
        ),
        _doc_meta(
            href_texto=_href_texto(UUID_TEXT_2),
            href_binario=_href_binario(UUID_BIN_2),
            idDocumento="doc-2",
            sequencia=2,
        ),
    ])

    # So registramos os mocks do PRIMEIRO documento. Se o codigo ignorasse
    # ``max_docs_per_process``, a request do 2o doc bateria sem mock e o
    # ``responses.activate`` falharia o teste.
    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )
    responses.add(
        responses.GET,
        f"{BASE_BINARY_URL}/{CNJ_DIGITS}/documentos/{UUID_BIN_1}/binario",
        body=load_sample_bytes("jusbr", "documents/binary_typical.bin"),
        status=200,
        content_type="application/pdf",
    )

    df = scraper.download_documents(base_df, max_docs_per_process=1)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert df.iloc[0]["idDocumento"] == "doc-1"


@responses.activate(registry=OrderedRegistry)
def test_download_documents_limite_e_independente_entre_processos(mocker):
    """Cotas independentes preservam a ordem de processos intercalados."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()
    documentos = [
        (CNJ_DIGITS, UUID_TEXT_1, "a-1"),
        (CNJ_DIGITS_2, UUID_BIN_1, "b-1"),
        (CNJ_DIGITS, UUID_TEXT_2, "a-2"),
        (CNJ_DIGITS_2, UUID_BIN_2, "b-2"),
        (CNJ_DIGITS, UUID_TEXT_3, "a-3"),
        (CNJ_DIGITS_2, UUID_TEXT_4, "b-3"),
    ]
    base_df = pd.concat(
        [
            _base_df(
                [
                    _doc_meta(
                        href_texto=_href_texto(uuid, numero_processo),
                        href_binario=None,
                        idDocumento=document_id,
                    ),
                ],
                numero_processo=numero_processo,
            )
            for numero_processo, uuid, document_id in documentos
        ],
        ignore_index=True,
    )
    for numero_processo, uuid, _ in documentos[:4]:
        responses.add(
            responses.GET,
            f"{BASE_TEXT_URL}/{numero_processo}/documentos/{uuid}/texto",
            body=load_sample("jusbr", "documents/text_typical.txt"),
            status=200,
        )

    df = scraper.download_documents(base_df, max_docs_per_process=2)

    assert df["numero_processo"].tolist() == [
        CNJ_DIGITS,
        CNJ_DIGITS_2,
        CNJ_DIGITS,
        CNJ_DIGITS_2,
    ]
    assert df["idDocumento"].tolist() == ["a-1", "b-1", "a-2", "b-2"]
    assert len(responses.calls) == 4


@responses.activate(registry=OrderedRegistry)
def test_download_documents_limite_zero_nao_baixa_nem_pausa(mocker):
    """Limite zero retorna vazio antes de iterar metadados ou fazer HTTP."""
    sleep = mocker.patch("time.sleep")
    scraper = _authenticated_scraper(sleep_time=0.25)
    base_df = _base_df([
        _doc_meta(
            href_texto=_href_texto(UUID_TEXT_1),
            href_binario=None,
            idDocumento="doc-1",
        ),
    ])

    df = scraper.download_documents(base_df, max_docs_per_process=0)

    assert df.empty
    assert not responses.calls
    sleep.assert_not_called()


@pytest.mark.parametrize(
    ("metadata_location", "expected_id", "expected_uuid"),
    [
        ("dados_basicos", "dados-basicos", UUID_TEXT_1),
        ("documentos", "documentos", UUID_TEXT_2),
        ("tramitacao_ndarray", "tramitacao", UUID_BIN_1),
        ("dados_basicos_invalido", "documentos", UUID_TEXT_2),
        ("documentos_invalido", "tramitacao", UUID_BIN_1),
    ],
)
@responses.activate(registry=OrderedRegistry)
def test_download_documents_respeita_prioridade_dos_caminhos_de_metadata(
    mocker, metadata_location, expected_id, expected_uuid
):
    """O primeiro caminho não vazio vence; ``tramitacaoAtual`` aceita ndarray."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()
    doc_dados_basicos = _doc_meta(
        href_texto=_href_texto(UUID_TEXT_1),
        href_binario=None,
        idDocumento="dados-basicos",
    )
    doc_documentos = _doc_meta(
        href_texto=_href_texto(UUID_TEXT_2),
        href_binario=None,
        idDocumento="documentos",
    )
    doc_tramitacao = _doc_meta(
        href_texto=_href_texto(UUID_BIN_1),
        href_binario=None,
        idDocumento="tramitacao",
    )
    detalhes: dict[str, Any] = {
        "dadosBasicos": {"documentos": [doc_dados_basicos]},
        "documentos": [doc_documentos],
        "tramitacaoAtual": {"documentos": [doc_tramitacao]},
    }
    if metadata_location == "documentos":
        detalhes["dadosBasicos"]["documentos"] = []
    elif metadata_location == "tramitacao_ndarray":
        detalhes["dadosBasicos"]["documentos"] = []
        detalhes["documentos"] = []
        detalhes["tramitacaoAtual"]["documentos"] = np.array([doc_tramitacao], dtype=object)
    elif metadata_location == "dados_basicos_invalido":
        detalhes["dadosBasicos"]["documentos"] = "container-malformado"
    elif metadata_location == "documentos_invalido":
        detalhes["dadosBasicos"]["documentos"] = []
        detalhes["documentos"] = {"container": "malformado"}

    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{expected_uuid}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )

    df = scraper.download_documents(_base_df_with_details(detalhes))

    assert df["idDocumento"].tolist() == [expected_id]


@responses.activate(registry=OrderedRegistry)
def test_download_documents_limite_conta_so_linhas_produzidas_e_sleep_so_apos_sucesso(mocker):
    """Metadata inválida ou sem UUID não consome limite nem dispara pausa."""
    sleep = mocker.patch("time.sleep")
    scraper = _authenticated_scraper(sleep_time=0.25)
    documentos = [
        "metadata-invalida",
        _doc_meta(href_texto=None, href_binario=None, idDocumento="sem-uuid"),
        _doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=None, idDocumento="valido-1"),
        _doc_meta(href_texto=_href_texto(UUID_TEXT_2), href_binario=None, idDocumento="valido-2"),
    ]
    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )

    df = scraper.download_documents(_base_df(documentos), max_docs_per_process=1)

    assert df["idDocumento"].tolist() == ["valido-1"]
    sleep.assert_called_once_with(0.25)


@responses.activate(registry=OrderedRegistry)
def test_download_documents_preserva_ordem_de_colunas_e_extras(mocker):
    """Metadados extras ficam ordenados antes das colunas preferenciais ausentes."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()
    documento = _doc_meta(
        href_texto=_href_texto(UUID_TEXT_1),
        href_binario=None,
        nome="Petição",
        zetaExtra=2,
        alphaExtra=1,
    )
    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=load_sample("jusbr", "documents/text_typical.txt"),
        status=200,
    )

    df = scraper.download_documents(_base_df([documento]))

    assert list(df.columns) == [
        "numero_processo",
        "idDocumento",
        "sequencia",
        "descricao",
        "nome",
        "tipo",
        "hrefTexto",
        "texto",
        "_raw_text_api",
        "_raw_binary_api",
        "alphaExtra",
        "zetaExtra",
        "idCodex",
        "tipoDocumento",
        "dataHoraJuntada",
        "dataJuntada",
        "nivelSigilo",
        "hrefBinario",
    ]
    assert df.loc[0, "alphaExtra"] == 1
    assert df.loc[0, "zetaExtra"] == 2


@responses.activate(registry=OrderedRegistry)
def test_download_documents_campos_calculados_prevalecem_sobre_metadata(mocker):
    """Metadados externos não sobrescrevem processo nem conteúdo baixado."""
    mocker.patch("time.sleep")
    scraper = _authenticated_scraper()
    documento = _doc_meta(
        href_texto=_href_texto(UUID_TEXT_1),
        href_binario=None,
        numero_processo="processo-incorreto",
        texto="texto-obsoleto",
        _raw_text_api="raw-obsoleto",
        _raw_binary_api=b"binario-obsoleto",
    )
    raw_text = "conteúdo real"
    responses.add(
        responses.GET,
        f"{BASE_TEXT_URL}/{CNJ_DIGITS}/documentos/{UUID_TEXT_1}/texto",
        body=raw_text,
        status=200,
    )

    df = scraper.download_documents(_base_df([documento]))

    assert df.loc[0, "numero_processo"] == CNJ_DIGITS
    assert df.loc[0, "texto"] == raw_text
    assert df.loc[0, "_raw_text_api"] == raw_text
    assert df.loc[0, "_raw_binary_api"] is None


def test_download_documents_sem_auth_levanta_runtime_error():
    """Sem ``auth(token)`` previo, ``download_documents`` aborta antes do loop."""
    scraper = jus.scraper("jusbr")
    base_df = _base_df([_doc_meta(href_texto=_href_texto(UUID_TEXT_1), href_binario=_href_binario(UUID_BIN_1))])
    with pytest.raises(RuntimeError, match=r"[Aa]utentica"):
        scraper.download_documents(base_df)


def test_download_documents_kwarg_desconhecido_levanta_type_error():
    """Kwarg desconhecido vira ``TypeError`` canonico via ``InputDownloadDocumentsJusBR``.

    A validacao do schema precede a checagem de auth, entao o ``TypeError`` sai
    sem ``auth()`` previo.
    """
    scraper = jus.scraper("jusbr")
    assert_unknown_kwarg_raises(scraper.download_documents, "kwarg_inventado", _base_df([]))


@pytest.mark.parametrize("base_df", [None, []])
def test_download_documents_rejeita_base_que_nao_e_dataframe(base_df):
    scraper = _authenticated_scraper()

    with pytest.raises(ValidationError, match="base_df"):
        scraper.download_documents(base_df)


def test_download_documents_rejeita_limite_negativo():
    scraper = _authenticated_scraper()

    with pytest.raises(ValidationError, match="max_docs_per_process"):
        scraper.download_documents(_base_df([]), max_docs_per_process=-1)
