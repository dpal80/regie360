"""Verifica in due passaggi con un'app di autenticazione (codici TOTP a 6 cifre, RFC 6238)."""

import hmac
import time

import pyotp
import segno

from app.models import Utente
from app.segreti import cifra, decifra

PASSO = 30  # secondi di validità di un codice


def prepara(utente: Utente) -> dict:
    """Crea un nuovo segreto (non ancora attivo) e restituisce quello che serve per configurare l'app."""
    segreto = pyotp.random_base32()
    utente.totp_segreto_cifrato = cifra(segreto)
    utente.totp_attivo = False
    utente.totp_ultimo_passo = None
    uri = pyotp.TOTP(segreto).provisioning_uri(name=utente.username, issuer_name="Regie360")
    return {"segreto": segreto, "qr_svg": segno.make(uri, error="m").svg_inline(scale=5, border=2)}


def verifica(utente: Utente, codice: str | None) -> bool:
    """Controlla il codice, accettando anche quello appena scaduto o il successivo (orologi non allineati).

    Un codice già usato non vale una seconda volta.
    """
    segreto = decifra(utente.totp_segreto_cifrato)
    cifre = "".join(c for c in (codice or "") if c.isdigit())
    if not segreto or len(cifre) != 6:
        return False
    totp = pyotp.TOTP(segreto)
    adesso = int(time.time()) // PASSO
    for passo in (adesso - 1, adesso, adesso + 1):
        if passo <= (utente.totp_ultimo_passo or 0):
            continue
        if hmac.compare_digest(totp.at(passo * PASSO), cifre):
            utente.totp_ultimo_passo = passo
            return True
    return False


def azzera(utente: Utente) -> None:
    utente.totp_segreto_cifrato = None
    utente.totp_attivo = False
    utente.totp_ultimo_passo = None
