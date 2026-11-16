"""Prazo e tentativas dos pedidos do eSAJ feitos direto na ``requests.Session``.

Valem para o cpopg e o cposg do TJSP e para o cjpg do eSAJ (TJSP e TJMS), que
não passam pelo retry de :class:`~juscraper.core.http.HTTPScraper`. O cjsg do
eSAJ segue a política dos ``perfis_http`` (ver :mod:`.download`).
"""

# Pedidos por processo (cpopg) ou por página (cjpg) antes de desistir. O cposg
# só usa o prazo.
TENTATIVAS = 5

# (conexão, leitura), em segundos, de cada pedido. Sem prazo, uma conexão que
# o eSAJ deixa aberta sem responder prende o lote inteiro, e o retry de
# cpopg_download_html_single nunca roda. O prazo estourado vira
# requests.Timeout, que o retry e _FALHAS_DE_DOCUMENTO já tratam (#484). A
# conexão curta faz o portal fora do ar falhar logo, sem 60 s por tentativa.
TIMEOUT = (10, 60)
