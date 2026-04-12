---
title: TJMA — Google reCAPTCHA v2 invisible
type: blocked
---

# TJMA Jurisconsult

The TJMA jurisprudence search at
<https://jurisconsult.tjma.jus.br/#/sg-jurisprudence-form> is an Angular
SPA that talks to `https://apijuris.tjma.jus.br/v1/...`. The search
endpoints (e.g. `/v1/sg/jurisprudencias/processos`) refuse every
request with

```json
{"error": "captcha_not_provided"}
```

unless a valid Google reCAPTCHA v2 invisible token is supplied in the
`tokenG` query parameter.

`/v1/util/site_infos?tipo=<hash>` returns:

```json
{"site_infos": {
    "str_public_key": "6LdM1m8cAAAAAOLISO2M2zo3-pbbImilMQfYwMmH",
    "str_hash_tipo": "cf70bdaf271e5e3c8495a92b8e57ace0",
    "int_habilitado": 1
}}
```

`int_habilitado: 1` signals that Google reCAPTCHA is the active
verification mode. The frontend also exposes a text captcha via
`/v1/util/gera_captcha` (JWT token + hex-encoded base64 JPEG, 5
alphanumeric characters), but it is **not** accepted on the search
endpoints while Google reCAPTCHA is enabled — every variant tested
(`tokenCaptcha`, `tokenG`, `captcha`, `g-recaptcha-response`, body
headers) returns the same `captcha_not_provided` error.

## Why juscraper cannot automate this site

Google reCAPTCHA v2 invisible is an interactive captcha. juscraper
only supports decorative captchas and text-based image captchas
(via [`txtcaptcha`](https://github.com/jtrecenti/txtcaptcha)). We do
not use paid anti-captcha services and do not ship browser-automation
based scrapers.

## Reproduction

```python
import requests

r = requests.get(
    "https://apijuris.tjma.jus.br/v1/sg/jurisprudencias/processos",
    params={
        "chave": "dano moral",
        "sistema": "0",
        "tipoPesquisa": "1",
        "relator": "0", "revisor": "0", "camara": "0",
        "condicao": "3", "classe": "0",
        "checkForm": "1",
        "dtaInicio": "2024-01-01",
        "dtaFim": "2024-12-31",
        "inicioPagina": "1", "fimPagina": "20",
        "tokenG": "0",
        "keyId": "cf70bdaf271e5e3c8495a92b8e57ace0",
    },
    headers={
        "User-Agent": "Mozilla/5.0",
        "Origin": "https://jurisconsult.tjma.jus.br",
        "Referer": "https://jurisconsult.tjma.jus.br/",
    },
    timeout=30,
)
assert r.json() == {"error": "captcha_not_provided"}
```

## Status

- **Date checked:** 2026-04-11
- **Type:** Google reCAPTCHA v2 invisible (interactive)
- **Backend validates token:** yes
- **Decision:** not supported
