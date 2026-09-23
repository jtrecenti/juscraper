"""Parsing das respostas do endpoint Falcao ``/no-auth/pesquisa``.

Cada colecao (:data:`.schemas.COLECOES`) devolve um shape proprio, mas todas
compartilham o mesmo envelope ``{documentos, quantidadeTotal, temasTopFive}``.
:func:`parse_documentos` normaliza um nucleo canonico comum (``processo``,
``colecao``, ``tribunal``, ``relator``, ``classe``, ``classe_sigla``,
``ementa``, ``data_julgamento``, ``data_juntada``) e propaga os demais campos
brutos da colecao, exceto os ``highlight*`` (ver :data:`_PREFIXO_HIGHLIGHT`).
"""
from __future__ import annotations

import logging
from typing import Any

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Chaves brutas candidatas a virar a coluna canonica ``classe`` (nome por
# extenso) — ordem de preferencia (a primeira presente vence). Colecoes
# distintas usam nomes diferentes para o mesmo conceito.
_CLASSE_KEYS: tuple[str, ...] = (
    "classeProcesso",
    "classeProcessualPorExtenso",
    "classeProcessual",
)

# Campos que o backend devolve para destacar o termo buscado (``<mark>``).
# Repetem o inteiro teor ou a ementa, e o inteiro teor carrega as imagens do
# documento em base64, entao manter os tres multiplicava o tamanho de cada
# linha. Ficam fora da saida; o texto integral segue em ``textoAcordao`` /
# ``textoSentenca`` / ``conteudoDecisao``.
_PREFIXO_HIGHLIGHT = "highlight"

# Abreviacao do ``tipo`` de precedente usada na chave ``processo``. Tipo fora
# do mapa entra na chave com o valor bruto do backend.
_TIPOS_PRECEDENTE: dict[str, str] = {
    "SUMULA": "SUM",
    "ORIENTACAO_JURISPRUDENCIAL": "OJ",
    "PRECEDENTE_NORMATIVO": "PN",
}

# No TST, cada orgao numera as proprias OJs a partir de 1, entao
# ``TST-OJ-130`` sozinho e ambiguo. A chave de OJ leva a sigla do orgao; OJ
# de orgao fora deste mapa leva o ``id`` do backend, que e unico.
_ORGAOS_OJ: dict[str, str] = {
    "Subseção I Especializada em Dissídios Individuais": "SBDI1",
    "Subseção II Especializada em Dissídios Individuais": "SBDI2",
    "Seção Especializada em Dissídios Coletivos": "SDC",
    "Tribunal Pleno": "TP",
}


def parse_total(data: dict[str, Any]) -> int:
    """Le ``quantidadeTotal`` do envelope JSON.

    Levanta ``ValueError`` quando a chave nao existe — sinal de que a API
    mudou de shape e o parser precisa acompanhar.
    """
    total = data.get("quantidadeTotal")
    if total is None:
        raise ValueError(
            "Resposta JSON do Falcao nao contem 'quantidadeTotal'."
        )
    return int(total)


def _chave_precedente(doc: dict[str, Any]) -> str | None:
    """Monta a chave legivel de um precedente, ex.: ``TST-SUM-392``.

    O ``numero`` sozinho se repete entre tipos (Sumula 392 x OJ 392) e entre
    tribunais, e falta em parte dos precedentes regionais. Sem ``tipo`` ou
    ``numero``, a chave cai para ``{tribunal}-id{id}``.
    """
    tribunal = doc.get("tribunal") or "?"
    tipo = doc.get("tipo")
    numero = doc.get("numero")
    ident = doc.get("id")
    if not tipo or numero in (None, ""):
        return f"{tribunal}-id{ident}" if ident is not None else None
    partes = [tribunal, _TIPOS_PRECEDENTE.get(tipo, tipo)]
    if tipo == "ORIENTACAO_JURISPRUDENCIAL":
        orgao = _ORGAOS_OJ.get(doc.get("orgaoJulgador") or "")
        if orgao is None:
            return f"{'-'.join(partes)}-{numero}-id{ident}"
        partes.append(orgao)
    partes.append(str(numero))
    return "-".join(partes)


def _texto_limpo(html: Any) -> str | None:
    """Converte a ementa HTML em texto corrido; vazia vira ``None``."""
    if not isinstance(html, str) or not html.strip():
        return None
    texto = " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())
    return texto or None


def _primeiro_nao_vazio(doc: dict[str, Any], *chaves: str) -> Any:
    for chave in chaves:
        valor = doc.get(chave)
        if valor not in (None, ""):
            return valor
    return None


def _normalizar_documento(raw: dict[str, Any], colecao: str) -> dict[str, Any]:
    """Aplica os renames canonicos a um documento bruto, preservando o resto."""
    doc = {k: v for k, v in raw.items() if not k.startswith(_PREFIXO_HIGHLIGHT)}

    # processo: numeroProcesso nas colecoes de decisao; 'precedentes' nao tem
    # processo e recebe a chave de _chave_precedente.
    if colecao == "precedentes":
        doc["processo"] = _chave_precedente(doc)
    else:
        doc["processo"] = doc.pop("numeroProcesso", None)

    doc["colecao"] = colecao
    doc["tribunal"] = doc.get("tribunal")

    # relator: 'acordaos' ja traz 'relator'. Nas demais, 'nomeRelator' vem
    # vazio quando o documento e de juiz singular (sentencas, decisoes
    # monocraticas) e o nome do magistrado fica em 'nomeRedator'.
    if not doc.get("relator"):
        doc["relator"] = _primeiro_nao_vazio(doc, "nomeRelator", "nomeRedator")

    # datas -> snake_case canonico.
    if "dataJulgamento" in doc:
        doc["data_julgamento"] = doc.pop("dataJulgamento")
    if "dataJuntada" in doc:
        doc["data_juntada"] = doc.pop("dataJuntada")

    # classe: nome por extenso, primeira chave bruta disponivel.
    if "classe" not in doc:
        doc["classe"] = _primeiro_nao_vazio(doc, *_CLASSE_KEYS)

    # classe_sigla: o valor que o filtro ``classe`` aceita. Acordaos e
    # decisoes monocraticas trazem 'siglaClasseProcesso'; sentencas e
    # recursos de revista trazem a sigla em 'classeProcessual', ao lado do
    # nome em 'classeProcessualPorExtenso'.
    sigla = doc.get("siglaClasseProcesso")
    if not sigla and doc.get("classeProcessualPorExtenso"):
        sigla = doc.get("classeProcessual")
    doc["classe_sigla"] = sigla or None

    if "ementa" in doc:
        doc["ementa"] = _texto_limpo(doc["ementa"])

    return doc


def parse_documentos(data: dict[str, Any], colecao: str) -> list[dict[str, Any]]:
    """Extrai e normaliza a lista ``documentos`` do envelope JSON.

    Args:
        data: JSON ja decodificado da resposta.
        colecao: Colecao consultada (usada para preencher a coluna ``colecao``
            e escolher os renames apropriados).

    Returns:
        Lista de dicionarios prontos para virar linhas de ``pd.DataFrame``,
        cada um com as colunas canonicas garantidas (:class:`.schemas.
        OutputCJSGFalcao`) alem dos campos brutos da colecao.
    """
    documentos = data.get("documentos")
    if documentos is None:
        return []
    return [_normalizar_documento(doc, colecao) for doc in documentos]
