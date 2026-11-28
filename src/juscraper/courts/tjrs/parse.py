"""Parse de resultados brutos da pesquisa de jurisprudência do TJRS."""
import json

import pandas as pd

from juscraper.core.exceptions import HTTPSemanticError, _RecriaSemInit
from juscraper.core.parse_utils import coerce_date_columns, normalizar_colunas_texto


class TJRSBuscaError(_RecriaSemInit, HTTPSemanticError):
    """O portal respondeu HTTP 200 sem ``response``: o Solr recusou a consulta.

    Observado ao vivo com aspas sem fechar e operador solto em ``pesquisa``
    (código 400 do Solr) e com página absurda (código 500): o corpo vem como
    ``{"error": "<JSON do Solr em texto>", ...}``. Sem este erro, a busca
    voltava vazia, como se não houvesse acórdãos.

    ``codigo`` é o código do Solr (``None`` se o envelope não o trouxer) e
    ``mensagem``, o texto do erro.
    """

    def __init__(self, mensagem: str, codigo: int | None = None) -> None:
        """Guarda ``mensagem`` e ``codigo`` e monta o texto do erro."""
        self.mensagem = mensagem
        self.codigo = codigo
        super().__init__(
            f"TJRS: a busca de jurisprudência devolveu erro em vez de resultados (código {codigo}): {mensagem}"
        )


def exigir_resultados(dados: object) -> dict:
    """Devolve ``dados`` se trouxer ``response``; senão, levanta :class:`TJRSBuscaError`."""
    if isinstance(dados, dict) and isinstance(dados.get("response"), dict):
        return dados
    raise _erro_da_busca(dados)


def _erro_da_busca(dados: object) -> TJRSBuscaError:
    """Monta o erro a partir do envelope sem ``response``."""
    erro = dados.get("error") if isinstance(dados, dict) else None
    if isinstance(erro, str):
        try:
            erro = json.loads(erro)
        except ValueError:
            return TJRSBuscaError(erro[:500])
    detalhe = erro.get("error") if isinstance(erro, dict) else None
    if isinstance(detalhe, dict) and detalhe.get("msg"):
        return TJRSBuscaError(str(detalhe["msg"]), detalhe.get("code"))
    return TJRSBuscaError("resposta sem a chave 'response'")


def clean_value(val: object) -> object:
    """Primeiro item de um campo multivalorado do Solr; o próprio valor nos demais."""
    if isinstance(val, list):
        return val[0] if val else None
    return val


def _relator(doc: dict) -> object:
    """Nome do relator.

    ``relator_redator`` traz o redator antes do relator quando são pessoas
    diferentes; ``nome_relator`` é sempre o relator.
    """
    return clean_value(doc.get('nome_relator')) or clean_value(doc.get('relator_redator'))


def cjsg_parse_manager(resultados_brutos: list) -> pd.DataFrame:
    """
    Extrai os dados relevantes dos resultados brutos retornados pelo TJRS.
    Retorna um DataFrame com as decisões.

    Raises:
        TJRSBuscaError: Um item é o envelope de erro do Solr, e não uma página
            de resultados; uma nota do erro diz a posição dele na lista.
    """
    resultados = []
    for posicao, bruto in enumerate(resultados_brutos):
        try:
            data = exigir_resultados(bruto)
        except TJRSBuscaError as exc:
            exc.add_note(f"cjsg_parse: é o item {posicao} da lista de páginas brutas.")
            raise
        docs = data['response'].get('docs', [])
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
                'relator': _relator(doc),
                'orgao_julgador': clean_value(doc.get('orgao_julgador')),
                'data_julgamento': clean_value(doc.get('data_julgamento')),
                'data_publicacao': clean_value(doc.get('data_publicacao')),
                'classe': clean_value(doc.get('nome_classe_cnj')),
                'assunto': clean_value(doc.get('nome_assunto_cnj')),
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
                'nome_redator': clean_value(doc.get('nome_redator')),
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
    coerce_date_columns(df, ["data_julgamento", "data_publicacao"])
    normalizar_colunas_texto(df, ["ementa", "ementa_text", "ementa_referencia"])
    principais = [
        'processo', 'relator', 'orgao_julgador', 'data_julgamento', 'data_publicacao',
        'classe', 'assunto', 'tribunal', 'tipo_processo', 'url', 'ementa',
        'documento_text'
    ]
    cols_principais = [c for c in principais if c in df.columns]
    cols_nao_principais = [c for c in df.columns if c not in principais]
    cols = cols_principais + cols_nao_principais
    df = df[cols]
    return df
