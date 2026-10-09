"""Semina locale: utenti di esempio per provare il CRM su un'installazione di prova.

Uso: docker compose exec backend python -m app.semina

Le password sono pubbliche (stanno nel repository): mai lanciarla sul server in sede.
"""

import sys

from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.db import SessionLocal
from app.models import ORIGINE_LOCALE, RUOLO_OPERATORE, RUOLO_RESPONSABILE, Utente
from app.security import hash_password, normalizza_username

# (username, nome, ruolo, interno, password)
UTENTI_DI_ESEMPIO = [
    ("resp.prova", "Giulia Bianchi (prova)", RUOLO_RESPONSABILE, "201", "Prova-Responsabile1"),
    ("op.rossi", "Marco Rossi (prova)", RUOLO_OPERATORE, "211", "Prova-Operatore1"),
    ("op.verdi", "Sara Verdi (prova)", RUOLO_OPERATORE, "212", "Prova-Operatore2"),
    ("op.neri", "Luca Neri (prova)", RUOLO_OPERATORE, "213", "Prova-Operatore3"),
]


def semina_utenti() -> list[str]:
    """Crea gli utenti di esempio che mancano; quelli già presenti non vengono toccati."""
    creati = []
    with SessionLocal() as db:
        for username, nome, ruolo, interno, password in UTENTI_DI_ESEMPIO:
            username = normalizza_username(username)
            creato = db.execute(
                insert(Utente)
                .values(
                    username=username,
                    nome=nome,
                    ruolo=ruolo,
                    origine=ORIGINE_LOCALE,
                    password_hash=hash_password(password),
                    # Niente cambio password al primo accesso: i test devono poter rientrare sempre.
                    deve_cambiare_password=False,
                    interno=interno,
                    attivo=True,
                    tentativi_falliti=0,
                )
                .on_conflict_do_nothing(index_elements=["username"])
                .returning(Utente.id)
            ).scalar()
            if creato:
                creati.append(username)
        db.commit()
    return creati


if __name__ == "__main__":
    if get_settings().ad_server:
        sys.exit("Semina annullata: con l'Active Directory configurato questa non è un'installazione di prova.")
    creati = semina_utenti()
    print("Utenti di esempio creati:", ", ".join(creati) if creati else "nessuno (c'erano già)")
