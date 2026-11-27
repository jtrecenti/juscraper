"""Querystring dos filtros de busca do agregador PDPJ.

Converte os nomes canonicos dos schemas (:mod:`.schemas`) para os nomes
camelCase que a API recebe em ``GET /api/v1/processos`` e
``/processos:contar``.
"""
from __future__ import annotations

from typing import Any

# Mapeia nomes canonicos snake_case -> nomes camelCase aceitos pela API.
# Compartilhado entre ``PdpjScraper.pesquisa`` e ``PdpjScraper.contar``
# (que aceita um subconjunto; ver ``InputContarPdpj``).
_QUERY_PARAM_MAP: dict[str, str] = {
    "numero_processo": "numeroProcesso",
    "numero_processo_sintetico": "numeroProcessoSintetico",
    "id": "id",
    "id_fonte_dados_codex": "idFonteDadosCodex",
    "cpf_cnpj_parte": "cpfCnpjParte",
    "nome_parte": "nomeParte",
    "outro_nome_parte": "outroNomeParte",
    "polo_parte": "poloParte",
    "situacao_parte": "situacaoParte",
    "nome_representante": "nomeRepresentante",
    "oab_representante": "oabRepresentante",
    "href": "href",
    "id_assunto_judicial": "idAssuntoJudicial",
    "id_classe": "idClasse",
    "id_orgao_julgador": "idOrgaoJulgador",
    "instancia": "instancia",
    "fase": "fase",
    "situacao_atual": "situacaoAtual",
    "segmento_justica": "segmentoJustica",
    "tribunal": "tribunal",
    "tipo_operacao": "tipoOperacao",
    "numero_historico": "numeroHistorico",
    "data_atualizacao_inicio": "dataHoraAtualizacaoInicio",
    "data_atualizacao_fim": "dataHoraAtualizacaoFim",
    "data_primeiro_ajuizamento_inicio": "dataHoraPrimeiroAjuizamentoInicio",
    "data_primeiro_ajuizamento_fim": "dataHoraPrimeiroAjuizamentoFim",
    "campo_ordenacao": "campoOrdenacao",
}


def _to_query_params(model_data: dict[str, Any]) -> dict[str, Any]:
    """Converte um dict com nomes canonicos para querystring camelCase.

    Valores ``None`` sao ignorados; listas viram strings com itens
    separados por virgula (formato esperado pela API).
    """
    out: dict[str, Any] = {}
    for key, value in model_data.items():
        if value is None:
            continue
        api_key = _QUERY_PARAM_MAP.get(key, key)
        if isinstance(value, list):
            out[api_key] = ",".join(str(v) for v in value)
        else:
            out[api_key] = value
    return out
