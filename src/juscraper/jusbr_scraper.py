from .base_scraper import BaseScraper
import requests
import time
import jwt
import pandas as pd
from tqdm import tqdm

class JUSBR_Scraper(BaseScraper):
    """Raspador para o Tribunal de Justiça do Brasil (genérico)."""

    def __init__(self, verbose=1, download_path=None, sleep_time=0.5, **kwargs):
        super().__init__("JUSBR")
        self.verbose = verbose
        self.download_path = download_path
        self.sleep_time = sleep_time
        self.session = requests.Session()
        self.token = None

    def auth(self, token: str, verbose=0):
        """
        Recebe o JWT token (access_token) já obtido manualmente pelo usuário.
        Decodifica o token e imprime as informações se verbose=1.
        Caso o token seja inválido, exibe tutorial para obtenção manual.
        """
        try:
            # PyJWT: decode sem verificação de assinatura
            decoded = jwt.decode(token, options={"verify_signature": False, "verify_aud": False}, algorithms=["RS256", "HS256", "none"])
            self.token = token
            if verbose == 1:
                print("Token JWT decodificado com sucesso! Informações do token:")
                for k, v in decoded.items():
                    print(f"  {k}: {v}")
            else:
                print("Token JWT decodificado com sucesso!")
        except Exception as e:
            print("Falha ao decodificar o token JWT. Erro:", str(e))
            print("\nCertifique-se de que o pacote PyJWT está instalado (uv add pyjwt).\n")
            print("Tutorial para obter o token JWT (access_token):\n")
            print("1. Acesse https://www.jus.br")
            print("2. Faça login usando o gov.br")
            print("3. Entre na página https://portaldeservicos.pdpj.jus.br/consulta (ou clique no botão 'Consultar processo', que aparece após o login)")
            print("4. Na nova página, abra a aba Network do navegador (F12 ou 'Inspecionar elemento')")
            print("5. Atualize a página (F5 ou ctrl+R ou no botão atualizar)")
            print("6. Nas requisições que vão aparecer, procure a requisição que tem nome 'token'. Clique nela.")
            print("7. Na tela ao lado, clique em 'Resposta'.")
            print("8. Selecione e copie o campo 'access_token' que aparece lá.")
            raise Exception("Token JWT inválido ou biblioteca errada. Siga o tutorial acima e use o pacote PyJWT.")

    def cpopg(self, id_cnj, method='html'):
        """
        Consulta processos pelo número CNJ (ou lista de números CNJ) via API nacional.
        Retorna um DataFrame do pandas com metadados e detalhes de cada processo.
        Inclui a coluna 'processo' (primeira coluna), com o número pesquisado (sempre limpo, só números).
        """
        import time
        import pandas as pd
        from .utils import clean_cnj
        if isinstance(id_cnj, str):
            id_cnj = [id_cnj]
        resultados = []
        headers = {
            'accept': 'application/json, text/plain, */*',
            'authorization': f'Bearer {self.token}',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
            'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
        }
        for cnj in id_cnj:
            cnj_limpo = clean_cnj(cnj)
            url1 = f'https://portaldeservicos.pdpj.jus.br/api/v2/processos?numeroProcesso={cnj}'
            r1 = self.session.get(url1, headers=headers)
            if r1.status_code != 200:
                raise Exception(f'Erro ao consultar processo {cnj}: {r1.status_code} {r1.text}')
            dados1 = r1.json()
            processos = dados1.get('content', [])
            for proc in processos:
                numero_proc = proc.get('numeroProcesso', cnj)
                url2 = f'https://portaldeservicos.pdpj.jus.br/api/v2/processos/{cnj}'
                r2 = self.session.get(url2, headers=headers)
                if r2.status_code != 200:
                    raise Exception(f'Erro ao consultar detalhes do processo {cnj}: {r2.status_code} {r2.text}')
                detalhes_proc = r2.json()
                row = {
                    'processo': cnj_limpo,
                    'numeroProcesso': numero_proc,
                    'idCodexTribunal': proc.get('idCodexTribunal'),
                    'detalhes': detalhes_proc
                }
                resultados.append(row)
                time.sleep(self.sleep_time)
        df = pd.DataFrame(resultados)
        # Garante a ordem da coluna 'processo' como primeira
        cols = ['processo'] + [c for c in df.columns if c != 'processo']
        return df[cols]

    def download_documents(self, base, sleep_time=None, verbose=0, log_path=None):
        """
        Baixa todos os autos/documentos em hrefTexto para cada processo da base (DataFrame do cpopg).
        Retorna um DataFrame onde cada linha é um documento com texto e metadados principais.
        Se log_path for fornecido, salva o log detalhado das tentativas.
        """
        import pandas as pd
        import time
        import logging
        import os
        import re
        session = self.session
        token = self.token
        if sleep_time is None:
            sleep_time = self.sleep_time
        # Configuração de logging
        logger = logging.getLogger("jusbr_download_documents")
        logger.handlers = []  # Remove handlers antigos
        logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
        if log_path:
            fh = logging.FileHandler(log_path, mode='w', encoding='utf-8')
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        if verbose:
            sh.setLevel(logging.INFO)
            logger.addHandler(sh)
        documentos = []
        headers = {
            'accept': '*/*',
            'authorization': f'Bearer {token}',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0',
            'referer': 'https://portaldeservicos.pdpj.jus.br/consulta',
        }
        if verbose:
            logger.info(f"Iniciando download de documentos para {len(base)} processos...")
        for idx, row in base.iterrows():
            numeroProcesso = row['numeroProcesso']
            detalhes = row['detalhes']
            docs = []
            # Correção: buscar documentos dentro de tramitacaoAtual
            if isinstance(detalhes, list):
                for item in detalhes:
                    ta = item.get('tramitacaoAtual', {})
                    docs.extend(ta.get('documentos', []))
            elif isinstance(detalhes, dict):
                ta = detalhes.get('tramitacaoAtual', {})
                docs = ta.get('documentos', [])
            else:
                if verbose:
                    logger.warning(f"Formato inesperado em detalhes para processo {numeroProcesso}: {type(detalhes)}")
            if verbose:
                logger.info(f"Processo {numeroProcesso}: {len(docs)} documentos encontrados.")
            for doc in docs:
                href = doc.get('hrefTexto')
                texto = None
                # Extrai o id do documento do hrefTexto
                id_href = None
                if href and '/documentos/' in href:
                    try:
                        id_href = href.split('/documentos/')[1].split('/')[0]
                    except Exception as e:
                        if verbose:
                            logger.warning(f"Não foi possível extrair id_href de hrefTexto={href}: {e}")
                # Novo endpoint alternativo para texto
                if id_href:
                    alt_url = (
                        f"https://api-processo.data-lake.pdpj.jus.br/processo-api/api/v1/processos/"
                        f"{numeroProcesso}/documentos/{id_href}/texto"
                        f"?numeroProcesso={numeroProcesso}&idDocumento={id_href}"
                    )
                    if verbose:
                        logger.info(f"Tentando baixar texto do documento via endpoint alternativo: {alt_url}")
                    try:
                        r = session.get(alt_url, headers=headers, timeout=15)
                        if r.status_code == 200:
                            # Garante o encoding correto e remove caracteres indesejados
                            try:
                                texto = r.content.decode('utf-8')
                            except Exception:
                                texto = r.text  # fallback
                            # Limpa caracteres de controle e normaliza quebras de linha
                            texto = re.sub(r'[\r\x00\x1a]', '', texto)
                            texto = texto.replace('\xa0', ' ').replace('\u2028', '\n').replace('\u2029', '\n')
                            if verbose:
                                logger.info(f"Sucesso ao baixar texto do doc {alt_url} (tamanho={len(texto)})")
                        else:
                            if verbose:
                                logger.warning(f"Falha ao baixar texto do doc {alt_url}: {r.status_code} {r.text[:200]}")
                    except Exception as e:
                        if verbose:
                            logger.error(f"Erro ao baixar texto do doc {alt_url}: {e}")
                    time.sleep(sleep_time)
                else:
                    if verbose:
                        logger.warning(f"Documento sem id_href extraído de hrefTexto: {doc}")
                linha = {**{k: doc.get(k) for k in doc}, 'numeroProcesso': numeroProcesso, 'texto': texto}
                documentos.append(linha)
        colunas = ['numeroProcesso', 'sequencia', 'dataHoraJuntada', 'idCodex', 'idOrigem', 'nome', 'nivelSigilo', 'tipo', 'hrefBinario', 'hrefTexto', 'arquivo', 'texto']
        df_docs = pd.DataFrame(documentos)
        for col in colunas:
            if col not in df_docs.columns:
                df_docs[col] = None
        if verbose:
            logger.info(f"Download finalizado. Total de documentos: {len(df_docs)}.")
        return df_docs[colunas]

    def cposg(self, process_number: str):
        pass

    def cjsg(self, query: str):
        pass
