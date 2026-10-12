"""Tiny stdlib HTTP helpers (python.org builds ship without CA certs, so use the system bundle)."""

import json
import os
import ssl
import urllib.request

SSL_CTX = ssl.create_default_context(cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)
UA = "Mozilla/5.0 (avers; personal use)"


def get_bytes(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        return r.read()


def get_json(url: str, timeout: float = 30):
    return json.loads(get_bytes(url, timeout))
