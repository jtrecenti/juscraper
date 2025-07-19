"""
Parse de resultados brutos da pesquisa de jurisprudência do TJRS.
"""
import pandas as pd

def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """
    Extrai os dados relevantes dos resultados brutos retornados pelo TJRS.
    Retorna um DataFrame com as decisões.
    """
    def clean_value(val):
        if isinstance(val, list):
            return val[0] if val else None
        return val
    resultados = []
    for data in resultados_brutos:
        docs = data.get('response', {}).get('docs', [])
        for doc in docs:
            url = (
                clean_value(doc.get('url_html')) or
                clean_value(doc.get('url_acordao')) or
                clean_value(doc.get('url'))
            )
            if not url and doc.get('numero_processo'):
                url = (
                    f"https://www.tjrs.jus.br/buscas/jurisprudencia/?numero_processo="
                    f"{clean_value(doc.get('numero_processo'))}"
                )
            resultado = {
                'processo': clean_value(doc.get('numero_processo')),
                'relator': clean_value(doc.get('relator_redator')),
                'orgao_julgador': clean_value(doc.get('orgao_julgador')),
                'data_julgamento': clean_value(doc.get('data_julgamento')),
                'data_publicacao': clean_value(doc.get('data_publicacao')),
                'classe_cnj': clean_value(doc.get('nome_classe_cnj')),
                'assunto_cnj': clean_value(doc.get('nome_assunto_cnj')),
                'tribunal': clean_value(doc.get('nome_tribunal')),
                'tipo_processo': clean_value(doc.get('tipo_processo')),
                'url': url,
                'ementa': clean_value(doc.get('ementa_completa')),
                # Novos campos:
                'documento_text': clean_value(doc.get('documento_text')),
                'documento_tiff': clean_value(doc.get('documento_tiff')),
                'ementa_text': clean_value(doc.get('ementa_text')),
                'mes_ano_publicacao': clean_value(doc.get('mes_ano_publicacao')),
                'origem': clean_value(doc.get('origem')),
                'secao': clean_value(doc.get('secao')),
                'ano_julgamento': clean_value(doc.get('ano_julgamento')),
                'nome_relator': clean_value(doc.get('nome_relator')),
                'ind_segredo_justica': clean_value(doc.get('ind_segredo_justica')),
                'ementa_referencia': clean_value(doc.get('ementa_referencia')),
                'cod_ementa': clean_value(doc.get('cod_ementa')),
                'cod_classe_cnj': clean_value(doc.get('cod_classe_cnj')),
                'cod_org_julg': clean_value(doc.get('cod_org_julg')),
                'cod_redator': clean_value(doc.get('cod_redator')),
                'cod_tipo_documento': clean_value(doc.get('cod_tipo_documento')),
                'cod_tribunal': clean_value(doc.get('cod_tribunal')),
                'cod_assunto_cnj': clean_value(doc.get('cod_assunto_cnj')),
                'cod_relator': clean_value(doc.get('cod_relator')),
                'cod_recurso': clean_value(doc.get('cod_recurso')),
                'tipo_documento': clean_value(doc.get('tipo_documento')),
                'dthr_criacao': clean_value(doc.get('dthr_criacao')),
                '_version_': clean_value(doc.get('_version_')),
            }
            resultados.append(resultado)
    df = pd.DataFrame(resultados)
    for col in ["data_julgamento", "data_publicacao"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    principais = [
        'processo', 'relator', 'orgao_julgador', 'data_julgamento', 'data_publicacao',
        'classe_cnj', 'assunto_cnj', 'tribunal', 'tipo_processo', 'url', 'ementa',
        'documento_text'
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_nao_principais = [c for c in df.columns if c not in principais]
    cols = cols_principais + cols_nao_principais
    df = df[cols]
    return df
