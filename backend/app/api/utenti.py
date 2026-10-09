from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import ORIGINE_AD, ORIGINE_LOCALE, RUOLI, Utente
from app.security import normalizza_username, solo_responsabile

router = APIRouter(prefix="/utenti", tags=["utenti"])


class UtenteOut(BaseModel):
    id: int
    username: str
    nome: str
    ruolo: str
    origine: str
    interno: str | None
    attivo: bool
    bloccato_fino: datetime | None
    ultimo_accesso: datetime | None

    model_config = {"from_attributes": True}


class UtenteNuovo(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    nome: str = Field(min_length=1, max_length=200)
    ruolo: str
    interno: str | None = Field(default=None, max_length=20)


class UtenteModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ruolo: str | None = None
    interno: str | None = Field(default=None, max_length=20)
    attivo: bool | None = None


def _controlla_ruolo(ruolo: str | None) -> None:
    if ruolo is not None and ruolo not in RUOLI:
        raise HTTPException(422, "Ruolo non valido")


@router.get("", response_model=list[UtenteOut])
def elenco(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return db.scalars(select(Utente).order_by(Utente.nome)).all()


@router.post("", response_model=UtenteOut, status_code=201)
def crea(
    dati: UtenteNuovo,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Abilita al CRM un utente di Active Directory (la password resta quella di dominio)."""
    _controlla_ruolo(dati.ruolo)
    username = normalizza_username(dati.username)
    if db.scalar(select(Utente).where(Utente.username == username)):
        raise HTTPException(409, "Questo utente è già presente nel CRM")
    utente = Utente(
        username=username,
        nome=dati.nome.strip(),
        ruolo=dati.ruolo,
        origine=ORIGINE_AD,
        interno=(dati.interno or "").strip() or None,
        attivo=True,
    )
    db.add(utente)
    db.flush()
    registra(db, "utente_creato", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio={"username": username, "ruolo": dati.ruolo}, request=request)
    db.commit()
    return utente


@router.patch("/{utente_id}", response_model=UtenteOut)
def modifica(
    utente_id: int,
    dati: UtenteModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    utente = db.get(Utente, utente_id)
    if utente is None:
        raise HTTPException(404, "Utente non trovato")
    _controlla_ruolo(dati.ruolo)
    if utente.id == io.id and (dati.attivo is False or (dati.ruolo and dati.ruolo != io.ruolo)):
        raise HTTPException(400, "Non puoi disattivare o cambiare ruolo a te stesso")
    if utente.origine == ORIGINE_LOCALE and (dati.attivo is False or dati.ruolo):
        raise HTTPException(400, "L'amministratore di emergenza non si può disattivare né cambiare ruolo")

    modifiche = dati.model_dump(exclude_unset=True)
    if "interno" in modifiche:
        modifiche["interno"] = (modifiche["interno"] or "").strip() or None
    for campo, valore in modifiche.items():
        setattr(utente, campo, valore)
    registra(db, "utente_modificato", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio=modifiche, request=request)
    db.commit()
    return utente


@router.post("/{utente_id}/sblocca", response_model=UtenteOut)
def sblocca(
    utente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    utente = db.get(Utente, utente_id)
    if utente is None:
        raise HTTPException(404, "Utente non trovato")
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra(db, "utente_sbloccato", utente=io, oggetto=f"utente:{utente.id}", request=request)
    db.commit()
    return utente
