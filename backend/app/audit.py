from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Audit, Utente


def ip_client(request: Request | None) -> str | None:
    if request is None:
        return None
    # Dietro il proxy Nginx l'IP reale arriva in X-Real-IP.
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


def registra(
    db: Session,
    azione: str,
    *,
    utente: Utente | None = None,
    username: str | None = None,
    oggetto: str | None = None,
    dettaglio: dict | None = None,
    request: Request | None = None,
) -> None:
    """Aggiunge una riga al registro attività. Il commit lo fa il chiamante."""
    db.add(
        Audit(
            utente_id=utente.id if utente else None,
            username=username or (utente.username if utente else None),
            azione=azione,
            oggetto=oggetto,
            dettaglio=dettaglio,
            ip=ip_client(request),
        )
    )
