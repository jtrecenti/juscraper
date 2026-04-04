"""
Parsing functions for TJMT jurisprudence search results.
"""
import re


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    if not text:
        return ""
    return re.sub(r"<[^>]+>", "", text).strip()


def cjsg_parse(resultados_brutos: list, tipo_consulta: str = "Acordao") -> list[dict]:
    """Extract structured records from raw TJMT API responses.

    Args:
        resultados_brutos: List of raw JSON dicts (one per page).
        tipo_consulta: ``"Acordao"`` or ``"DecisaoMonocratica"``.

    Returns:
        List of flat dicts ready for ``pd.DataFrame``.
    """
    collection_key = "AcordaoCollection" if tipo_consulta == "Acordao" else "DecisaoMonocraticaCollection"

    registros = []
    for page_data in resultados_brutos:
        items = page_data.get(collection_key, [])
        for item in items:
            proc = item.get("Processo", {})
            registros.append({
                "id": item.get("Id"),
                "tipo": item.get("Tipo"),
                "ementa": _strip_html(item.get("Conteudo", "")),
                "observacao": item.get("Observacao"),
                "numero_unico": proc.get("NumeroUnicoFormatado"),
                "classe": proc.get("NomeClasseEsferaProcessual"),
                "assunto": proc.get("Assunto"),
                "tipo_acao": proc.get("TipoAcao"),
                "tipo_processo": proc.get("TipoProcesso"),
                "relator": proc.get("NomeRelator"),
                "redator_designado": proc.get("NomeRedatorDesignado"),
                "orgao_julgador": proc.get("DescricaoCamara"),
                "sigla_classe_feito": proc.get("SiglaClasseFeito"),
                "data_julgamento": proc.get("DataJulgamento"),
                "data_publicacao": proc.get("DataPublicacao"),
                "instancia": proc.get("Instancia"),
                "origem": proc.get("Origem"),
                "julgamento": proc.get("Julgamento"),
            })
    return registros
