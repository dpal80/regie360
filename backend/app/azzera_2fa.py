"""Toglie la verifica in due passaggi a un utente che ha perso il telefono.

Serve per l'amministratore globale, che nessun altro può modificare dal CRM:
    docker compose exec backend python -m app.azzera_2fa admin
"""

import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Utente
from app.security import normalizza_username
from app.services.duefattori import azzera

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Uso: python -m app.azzera_2fa <nome utente>")
    with SessionLocal() as db:
        utente = db.scalar(select(Utente).where(Utente.username == normalizza_username(sys.argv[1])))
        if utente is None:
            sys.exit("Utente non trovato")
        azzera(utente)
        db.commit()
    print(f"Verifica in due passaggi disattivata per {utente.username}.")
