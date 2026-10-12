"""Cifratura dei segreti che il CRM deve conservare (token del telefono, chiave dell'app Microsoft 365)."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _cifrario() -> Fernet:
    # Chiave derivata da JWT_SECRET: se cambia, i segreti salvati vanno reinseriti.
    chiave = hashlib.sha256(b"regie360-telefonia:" + get_settings().jwt_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(chiave))


def cifra(testo: str) -> str:
    return _cifrario().encrypt(testo.encode()).decode()


def decifra(cifrato: str | None) -> str | None:
    """Restituisce None se il valore manca o non si decifra più (JWT_SECRET cambiata)."""
    if not cifrato:
        return None
    try:
        return _cifrario().decrypt(cifrato.encode()).decode()
    except (InvalidToken, ValueError):
        return None
