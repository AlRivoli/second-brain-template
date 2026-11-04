"""Piccole utilità di rete con la sola libreria standard."""
import ssl
from pathlib import Path

CERTIFICATI = ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt")


def contesto_tls():
    """Contesto TLS. Il Python di python.org su macOS non porta i certificati: se l'archivio è vuoto si usano quelli del sistema."""
    c = ssl.create_default_context()
    if not c.cert_store_stats()["x509_ca"]:
        for file in CERTIFICATI:
            if Path(file).is_file():
                return ssl.create_default_context(cafile=file)
    return c
