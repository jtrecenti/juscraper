---
title: TJSE — Cloudflare Turnstile
type: blocked
---

# TJSE Jurisprudence Search

The TJSE jurisprudence search at
<https://www.tjse.jus.br/Dgorg/paginas/jurisprudencia/consultarJurisprudencia.tjse>
uses **Cloudflare Turnstile**, an interactive captcha, and the backend
**does validate the token**. A POST without a valid
`cf-turnstile-response` field returns an HTTP 200 page with the error
message:

```
<span class="ui-messages-error-summary">Captcha inválido</span>
```

## Why juscraper cannot automate this site

Cloudflare Turnstile is an interactive captcha — it relies on browser
fingerprinting, JavaScript execution, and Cloudflare challenge flows
to issue tokens. The juscraper project only supports:

1. Sites whose captcha is decorative (backend does not validate the
   token). TJRJ and TJGO fall in this group.
2. Sites with text-based image captchas that can be decoded by
   [`txtcaptcha`](https://github.com/jtrecenti/txtcaptcha).

Interactive captchas such as Turnstile, reCAPTCHA v2/v3 and hCaptcha
are explicitly out of scope. We do not use paid anti-captcha services
and do not ship browser-automation-based scrapers.

## Reproduction

```python
import requests, re

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})
r = s.get(
    "https://www.tjse.jus.br/Dgorg/paginas/jurisprudencia/"
    "consultarJurisprudencia.tjse",
    timeout=60,
)
vs = re.search(
    r'name="javax\.faces\.ViewState"[^>]*value="([^"]+)"', r.text
).group(1)
data = {
    "frmPrincipal": "frmPrincipal",
    "itTermos": "dano moral",
    "sorTipoDocumento": "AC",
    "sorCompetencia": "SG",
    "sorTipoPeriodo": "DI",
    "cf-turnstile-response": "",
    "btPesquisar": "",
    "javax.faces.ViewState": vs,
}
r2 = s.post(r.url, data=data, timeout=60)
assert "Captcha inv" in r2.text  # server-side validation
```

## Status

- **Date checked:** 2026-04-11
- **Type:** Cloudflare Turnstile (interactive)
- **Backend validates token:** yes
- **Decision:** not supported
