"""Capture cpopg + documents samples for the JusBR aggregator.

Run from repo root::

    JUSBR_JWT=<token-do-pdpj> python -m tests.fixtures.capture.jusbr

Optional env vars (defaults entre parenteses):

- ``JUSBR_CNJ_1`` — CNJ real para o cenario typical (obrigatorio).
- ``JUSBR_CNJ_2`` — segundo CNJ real para o cenario ``list[str]`` (obrigatorio).
- ``JUSBR_CNJ_NO_RESULTS`` — CNJ com formato valido mas sem processo no PDPJ
  (default: ``9999999-99.9999.9.99.9999``).

**Sanitizacao agressiva** acontece pos-captura, antes de gravar os arquivos:

1. Todo CNJ real (com ou sem mascara) e substituido por um CNJ neutro
   coordenado com os contratos (``00000000000000000000`` no cenario typical
   e ``11111111111111111111`` no cenario list[str]). As constantes
   ``NEUTRAL_CNJ_*`` aqui batem com as do contrato em
   ``tests/jusbr/test_cpopg_contract.py``.
2. Campos com PII (``nome``, ``cpf``, ``cnpj``, ``email``, ``telefone``,
   ``endereco``, etc.) sao substituidos por ``"REDACTED"``.
3. Campos textuais longos (``ementa``, ``descricao``, ``decisao``, ...) sao
   truncados em 80 chars + ``"..."``.

Os samples gravados sao usados pelos contratos em ``tests/jusbr/`` via
``responses``. O script **nao roda no pytest** — e ferramenta de manutencao.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from juscraper.aggregators.jusbr.client import JusbrScraper
from juscraper.utils.cnj import clean_cnj

from ._util import dump, samples_dir_for

# Coordenado com tests/jusbr/test_cpopg_contract.py — qualquer mudanca aqui
# tem que bater com os contratos (e vice-versa).
NEUTRAL_CNJ_1_DIGITS = "00000000000000000000"
NEUTRAL_CNJ_2_DIGITS = "11111111111111111111"
NEUTRAL_CNJ_NO_RESULTS_DIGITS = "99999999999999999999"

# Campos PII a redatar (lowercase para comparacao case-insensitive).
_PII_KEYS = {
    "nome",
    "cpf",
    "cnpj",
    "documentoprincipal",
    "documento",
    "email",
    "telefone",
    "celular",
    "endereco",
    "logradouro",
    "bairro",
    "cep",
    "complemento",
    "rg",
    "passaporte",
    "numerooab",
    "oab",
}

# Campos textuais a truncar (preserva shape, descarta conteudo do processo).
_TRUNCATE_KEYS = {
    "textocompleto",
    "ementa",
    "decisao",
    "fundamentacao",
    "descricao",
    "texto",
    "html",
    "conteudo",
}
_TRUNCATE_LEN = 80


def _sanitize_string(value: str, replacements: dict[str, str]) -> str:
    """Substitui CNJs reais por neutros em qualquer string."""
    out = value
    for real, neutral in replacements.items():
        out = out.replace(real, neutral)
    return out


def _redact_value(key_lower: str, value: Any, replacements: dict[str, str]) -> Any:
    if key_lower in _PII_KEYS:
        return "REDACTED" if value not in (None, "", []) else value
    if key_lower in _TRUNCATE_KEYS and isinstance(value, str) and len(value) > _TRUNCATE_LEN:
        return value[:_TRUNCATE_LEN] + "..."
    if isinstance(value, str):
        return _sanitize_string(value, replacements)
    return value


def _walk(obj: Any, replacements: dict[str, str]) -> Any:
    """Walk dict/list recursively applying redaction + CNJ replacement."""
    if isinstance(obj, dict):
        return {
            k: _walk(_redact_value(k.lower(), v, replacements), replacements)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_walk(item, replacements) for item in obj]
    if isinstance(obj, str):
        return _sanitize_string(obj, replacements)
    return obj


def _build_replacements(real_cnj: str, neutral_digits: str) -> dict[str, str]:
    """CNJ pode aparecer com ou sem pontuacao; cobre ambos."""
    real_digits = clean_cnj(real_cnj)
    return {real_cnj: _format_neutral(neutral_digits), real_digits: neutral_digits}


def _format_neutral(digits: str) -> str:
    """Volta para o formato canonico NNNNNNN-DD.AAAA.J.TR.OOOO."""
    if len(digits) != 20:
        return digits
    return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13:14]}.{digits[14:16]}.{digits[16:]}"


def _save_json(path: Path, data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    dump(path, payload)


def _capture_cpopg_pair(
    scraper: JusbrScraper,
    *,
    real_cnj: str,
    neutral_digits: str,
) -> tuple[dict, dict | None, str | None]:
    """Hit list+details endpoints raw (bypassa o parser para preservar shape)."""
    cnj_clean = clean_cnj(real_cnj)
    list_url = f"{scraper.BASE_API_URL_V2}?numeroProcesso={cnj_clean}"
    list_resp = scraper.session.get(list_url, timeout=30)
    list_resp.raise_for_status()
    list_data = list_resp.json()

    content = list_data.get("content") or []
    if not content:
        return list_data, None, None

    numero_oficial = content[0]["numeroProcesso"]
    details_url = f"{scraper.BASE_API_URL_V2}{numero_oficial}"
    details_resp = scraper.session.get(details_url, timeout=30)
    details_resp.raise_for_status()
    details_data = details_resp.json()
    return list_data, details_data, numero_oficial


def _replace_numero_processo_in_list(list_data: dict, neutral_digits: str) -> dict:
    """Garante que ``content[*].numeroProcesso`` use o CNJ neutro.

    Necessario porque o contrato extrai ``numero_oficial`` desse campo para
    montar o mock da URL de detalhes.
    """
    content = list_data.get("content") or []
    for item in content:
        if isinstance(item, dict):
            item["numeroProcesso"] = neutral_digits
    return list_data


def _replace_numero_processo_in_details(details_data: Any, neutral_digits: str) -> Any:
    if isinstance(details_data, list):
        return [_replace_numero_processo_in_details(d, neutral_digits) for d in details_data]
    if isinstance(details_data, dict):
        if "numeroProcesso" in details_data:
            details_data["numeroProcesso"] = neutral_digits
    return details_data


def _capture_document_payloads(
    scraper: JusbrScraper,
    *,
    details_data: Any,
    cnj_clean: str,
) -> tuple[bytes | None, bytes | None]:
    """Pega o primeiro documento com texto+binario nos detalhes."""
    doc_meta = _first_document_with_both_hrefs(details_data)
    if not doc_meta:
        return None, None

    href_texto = doc_meta["hrefTexto"]
    href_binario = doc_meta["hrefBinario"]
    uuid_texto = href_texto.split("/documentos/")[1].split("/")[0]
    uuid_binario = href_binario.split("/documentos/")[1].split("/")[0]

    text_url = (
        f"{scraper.BASE_API_URL_V1_DOCS.rstrip('/')}/{cnj_clean}/documentos/{uuid_texto}/texto"
        f"?numeroProcesso={cnj_clean}&idDocumento={uuid_texto}"
    )
    binary_url = (
        f"{scraper.BASE_API_URL_V2.rstrip('/')}/{cnj_clean}/documentos/{uuid_binario}/binario"
    )

    text_resp = scraper.session.get(text_url, timeout=30)
    text_resp.raise_for_status()

    binary_resp = scraper.session.get(binary_url, timeout=30)
    binary_resp.raise_for_status()
    return text_resp.content, binary_resp.content


def _first_document_with_both_hrefs(details_data: Any) -> dict | None:
    details_dict = details_data[0] if isinstance(details_data, list) and details_data else details_data
    if not isinstance(details_dict, dict):
        return None
    for path in (
        ("dadosBasicos", "documentos"),
        ("documentos",),
        ("tramitacaoAtual", "documentos"),
    ):
        cur: Any = details_dict
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                cur = None
                break
            cur = cur[key]
        if not isinstance(cur, list):
            continue
        for doc in cur:
            if isinstance(doc, dict) and doc.get("hrefTexto") and doc.get("hrefBinario"):
                return doc
    return None


def _sanitize_text_blob(raw: bytes, replacements: dict[str, str]) -> bytes:
    """Trunca e remove PII obvio (CPF, e-mail) do texto do documento."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    text = _sanitize_string(text, replacements)
    # Remove CPFs e e-mails residuais (regex defensivo, alem da redacao por chave).
    text = re.sub(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}", "[CPF_REDACTED]", text)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL_REDACTED]", text)
    if len(text) > 2000:
        text = text[:2000] + "\n[...truncated by capture script...]"
    return text.encode("utf-8")


def main() -> None:
    jwt_token = os.environ.get("JUSBR_JWT")
    if not jwt_token:
        raise SystemExit(
            "JUSBR_JWT env var e obrigatoria — exporte um JWT valido do PDPJ "
            "(devtools do navegador logado em portaldeservicos.pdpj.jus.br)."
        )

    cnj_1 = os.environ.get("JUSBR_CNJ_1")
    cnj_2 = os.environ.get("JUSBR_CNJ_2")
    cnj_no_results = os.environ.get("JUSBR_CNJ_NO_RESULTS", "9999999-99.9999.9.99.9999")

    if not cnj_1 or not cnj_2:
        raise SystemExit(
            "JUSBR_CNJ_1 e JUSBR_CNJ_2 sao obrigatorios — exporte 2 CNJs reais "
            "que existam no PDPJ. Eles serao sanitizados antes de virar sample."
        )

    scraper = JusbrScraper(sleep_time=0.5)
    scraper.auth(jwt_token)

    cpopg_dest = samples_dir_for("jusbr", "cpopg")
    docs_dest = samples_dir_for("jusbr", "documents")

    # --- Cenario: typical_single (lista + detalhes) ---
    print(f"[jusbr] capturing typical_single para {cnj_1!r}...")
    list_data, details_data, _ = _capture_cpopg_pair(
        scraper, real_cnj=cnj_1, neutral_digits=NEUTRAL_CNJ_1_DIGITS
    )
    if not details_data:
        raise SystemExit(f"JUSBR_CNJ_1={cnj_1!r} nao retornou processo no PDPJ.")

    # Captura documentos ANTES de sanitizar — usa URLs reais.
    cnj_1_clean = clean_cnj(cnj_1)
    text_blob, binary_blob = _capture_document_payloads(
        scraper, details_data=details_data, cnj_clean=cnj_1_clean
    )

    repl_1 = _build_replacements(cnj_1, NEUTRAL_CNJ_1_DIGITS)
    list_data = _replace_numero_processo_in_list(_walk(list_data, repl_1), NEUTRAL_CNJ_1_DIGITS)
    details_data = _replace_numero_processo_in_details(_walk(details_data, repl_1), NEUTRAL_CNJ_1_DIGITS)
    _save_json(cpopg_dest / "typical_single.json", list_data)
    _save_json(cpopg_dest / "typical_single_details.json", details_data)
    print("[jusbr] wrote cpopg/typical_single.json + typical_single_details.json")

    # --- Cenario: documents/text_typical + binary_typical ---
    if text_blob is None or binary_blob is None:
        print("[jusbr] WARN: nao encontrou documento com ambos hrefs; pulando documents/")
    else:
        sanitized_text = _sanitize_text_blob(text_blob, repl_1)
        dump(docs_dest / "text_typical.txt", sanitized_text)
        # Decisao 3 do plano: salvar PDF inteiro (sem truncar). Tipico: 50-500 KB.
        dump(docs_dest / "binary_typical.bin", binary_blob)
        print(
            f"[jusbr] wrote documents/text_typical.txt ({len(sanitized_text)} bytes) "
            f"+ binary_typical.bin ({len(binary_blob)} bytes)"
        )

    # --- Cenario: list_two ---
    print(f"[jusbr] capturing list_two para {cnj_1!r} + {cnj_2!r}...")
    list1, det1, _ = _capture_cpopg_pair(scraper, real_cnj=cnj_1, neutral_digits=NEUTRAL_CNJ_1_DIGITS)
    list2, det2, _ = _capture_cpopg_pair(scraper, real_cnj=cnj_2, neutral_digits=NEUTRAL_CNJ_2_DIGITS)
    if not det1 or not det2:
        raise SystemExit("Algum dos CNJs do list_two nao retornou processo.")

    repl_2 = _build_replacements(cnj_2, NEUTRAL_CNJ_2_DIGITS)
    list1 = _replace_numero_processo_in_list(_walk(list1, repl_1), NEUTRAL_CNJ_1_DIGITS)
    det1 = _replace_numero_processo_in_details(_walk(det1, repl_1), NEUTRAL_CNJ_1_DIGITS)
    list2 = _replace_numero_processo_in_list(_walk(list2, repl_2), NEUTRAL_CNJ_2_DIGITS)
    det2 = _replace_numero_processo_in_details(_walk(det2, repl_2), NEUTRAL_CNJ_2_DIGITS)
    _save_json(cpopg_dest / "list_two_first.json", list1)
    _save_json(cpopg_dest / "list_two_first_details.json", det1)
    _save_json(cpopg_dest / "list_two_second.json", list2)
    _save_json(cpopg_dest / "list_two_second_details.json", det2)
    print("[jusbr] wrote cpopg/list_two_*.json (4 arquivos)")

    # --- Cenario: no_results ---
    print(f"[jusbr] capturing no_results para {cnj_no_results!r}...")
    no_list, no_det, _ = _capture_cpopg_pair(
        scraper, real_cnj=cnj_no_results, neutral_digits=NEUTRAL_CNJ_NO_RESULTS_DIGITS
    )
    if no_det is not None:
        print(
            f"[jusbr] WARN: JUSBR_CNJ_NO_RESULTS={cnj_no_results!r} retornou processo. "
            "Escolha outro CNJ valido mas sem hit no PDPJ."
        )
    repl_nr = _build_replacements(cnj_no_results, NEUTRAL_CNJ_NO_RESULTS_DIGITS)
    no_list = _walk(no_list, repl_nr)
    _save_json(cpopg_dest / "no_results.json", no_list)
    print("[jusbr] wrote cpopg/no_results.json")

    print(f"[jusbr] ALL samples written under {cpopg_dest.parent}")


if __name__ == "__main__":
    main()
    sys.exit(0)
