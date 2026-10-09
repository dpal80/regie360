"""Semina locale: utenti di esempio per provare il CRM su un'installazione di prova.

Uso: docker compose exec backend python -m app.semina

Le password sono pubbliche (stanno nel repository): mai lanciarla sul server in sede.
"""

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ORIGINE_LOCALE, RUOLO_OPERATORE, RUOLO_RESPONSABILE, RUOLO_SUPERADMIN, Utente
from app.security import config_ad, hash_password, normalizza_username

# (username, nome, ruolo, interno, password): password facili da ricordare, solo per le prove.
UTENTI_DI_ESEMPIO = [
    ("super.prova", "Paolo Gialli (prova)", RUOLO_SUPERADMIN, "200", "pass-super"),
    ("resp.prova", "Giulia Bianchi (prova)", RUOLO_RESPONSABILE, "201", "pass-resp"),
    ("op.rossi", "Marco Rossi (prova)", RUOLO_OPERATORE, "211", "pass-rossi"),
    ("op.verdi", "Sara Verdi (prova)", RUOLO_OPERATORE, "212", "pass-verdi"),
    ("op.neri", "Luca Neri (prova)", RUOLO_OPERATORE, "213", "pass-neri"),
]


def semina_utenti() -> list[str]:
    """Crea gli utenti di esempio che mancano e riporta la password di esempio su quelli che ci sono già."""
    creati = []
    with SessionLocal() as db:
        for username, nome, ruolo, interno, password in UTENTI_DI_ESEMPIO:
            username = normalizza_username(username)
            esistente = db.scalar(select(Utente).where(Utente.username == username))
            if esistente is not None:
                if esistente.origine == ORIGINE_LOCALE:
                    esistente.password_hash = hash_password(password)
                    esistente.deve_cambiare_password = False
                    esistente.tentativi_falliti = 0
                    esistente.bloccato_fino = None
                continue
            db.add(Utente(
                username=username, nome=nome, ruolo=ruolo, origine=ORIGINE_LOCALE,
                password_hash=hash_password(password),
                # Niente cambio password al primo accesso: i test devono poter rientrare sempre.
                deve_cambiare_password=False, interno=interno, attivo=True, tentativi_falliti=0,
            ))
            creati.append(username)
        db.commit()
    return creati


if __name__ == "__main__":
    if config_ad().server:
        sys.exit("Semina annullata: con l'Active Directory configurato questa non è un'installazione di prova.")
    creati = semina_utenti()
    print("Utenti di esempio creati:", ", ".join(creati) if creati else "nessuno (c'erano già)")
    print("Password di esempio ripristinate per tutti gli utenti di prova.")
