"""
Downloads decisions from the TJSP CJSG.
"""
import os

from ...utils import safe_path_component


class AcordaoDownloadError(Exception):
    """Error downloading decision from TJSP CJSG."""


def download_acordao(
    cd_acordao,
    session,
    u_base,
    download_path,
):
    """
    Downloads a decision from the TJSP CJSG.
    """
    u = f"{u_base}/cjsg/getArquivo.do"
    query = {
        'cdAcordao': cd_acordao,
        'cdForo': 0
    }
    r = session.get(u, params=query)
    if r.status_code != 200:
        raise AcordaoDownloadError(f"Erro ao baixar o acordão {cd_acordao}: {r.status_code}")
    safe_cd = safe_path_component(cd_acordao, field="cdAcordao")
    path = os.path.join(download_path, "cjsg", f"{safe_cd}.pdf")
    # create folder if it doesn't exist
    if not os.path.isdir(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path))
    with open(path, 'wb') as f:
        f.write(r.content)
    return r
