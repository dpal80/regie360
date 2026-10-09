from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import ORIGINE_AD, ORIGINE_LOCALE, RUOLI, RUOLO_SUPERADMIN, Utente
from app.config import get_settings
from app.security import (
    PASSWORD_MIN,
    hash_password,
    normalizza_username,
    solo_responsabile,
    solo_superadmin,
)

router = APIRouter(prefix="/utenti", tags=["utenti"])


class UtenteOut(BaseModel):
    id: int
    username: str
    nome: str
    ruolo: str
    origine: str
    interno: str | None
    attivo: bool
    deve_cambiare_password: bool
    bloccato_fino: datetime | None
    ultimo_accesso: datetime | None
    admin_emergenza: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def da(cls, utente: Utente) -> "UtenteOut":
        return cls.model_validate(utente).model_copy(update={"admin_emergenza": _admin_emergenza(utente)})


class UtenteNuovo(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    nome: str = Field(min_length=1, max_length=200)
    ruolo: str
    interno: str | None = Field(default=None, max_length=20)
    origine: str = ORIGINE_AD
    # Solo per gli utenti locali: password provvisoria, da cambiare al primo accesso.
    password: str | None = Field(default=None, max_length=256)


class ResetPassword(BaseModel):
    password: str = Field(min_length=PASSWORD_MIN, max_length=256)


class UtenteModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ruolo: str | None = None
    interno: str | None = Field(default=None, max_length=20)
    attivo: bool | None = None


def _controlla_ruolo(ruolo: str | None) -> None:
    if ruolo is not None and ruolo not in RUOLI:
        raise HTTPException(422, "Ruolo non valido")


def _controlla_superadmin(io: Utente, utente: Utente | None, nuovo_ruolo: str | None) -> None:
    """Solo un super-admin può nominare un super-admin o toccare l'utente di un altro super-admin."""
    if io.superadmin:
        return
    if nuovo_ruolo == RUOLO_SUPERADMIN or (utente is not None and utente.superadmin):
        raise HTTPException(403, "Operazione riservata al super-admin")


def _controlla_admin_globale(utente: Utente) -> None:
    if utente.admin_globale:
        raise HTTPException(400, "L'amministratore globale non può essere modificato")


def _admin_emergenza(utente: Utente) -> bool:
    return utente.origine == ORIGINE_LOCALE and utente.username == normalizza_username(
        get_settings().admin_username
    )


def _controlla_password(password: str | None) -> str:
    if not password or len(password) < PASSWORD_MIN:
        raise HTTPException(422, f"La password deve avere almeno {PASSWORD_MIN} caratteri")
    return password


@router.get("", response_model=list[UtenteOut])
def elenco(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return [UtenteOut.da(u) for u in db.scalars(select(Utente).order_by(Utente.nome))]


@router.post("", response_model=UtenteOut, status_code=201)
def crea(
    dati: UtenteNuovo,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Abilita al CRM un utente di dominio (password di Windows) o crea un utente locale."""
    _controlla_ruolo(dati.ruolo)
    _controlla_superadmin(io, None, dati.ruolo)
    if dati.origine not in (ORIGINE_AD, ORIGINE_LOCALE):
        raise HTTPException(422, "Tipo di accesso non valido")
    password_hash = None
    if dati.origine == ORIGINE_LOCALE:
        password_hash = hash_password(_controlla_password(dati.password))
    username = normalizza_username(dati.username)
    if db.scalar(select(Utente).where(Utente.username == username)):
        raise HTTPException(409, "Questo utente è già presente nel CRM")
    utente = Utente(
        username=username,
        nome=dati.nome.strip(),
        ruolo=dati.ruolo,
        origine=dati.origine,
        password_hash=password_hash,
        deve_cambiare_password=dati.origine == ORIGINE_LOCALE,
        interno=(dati.interno or "").strip() or None,
        attivo=True,
    )
    db.add(utente)
    db.flush()
    registra(db, "utente_creato", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio={"username": username, "ruolo": dati.ruolo, "origine": dati.origine},
             request=request)
    db.commit()
    return UtenteOut.da(utente)


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
    _controlla_superadmin(io, utente, dati.ruolo)
    _controlla_admin_globale(utente)
    if utente.id == io.id and (dati.attivo is False or (dati.ruolo and dati.ruolo != io.ruolo)):
        raise HTTPException(400, "Non puoi disattivare o cambiare ruolo a te stesso")
    if _admin_emergenza(utente) and (dati.attivo is False or (dati.ruolo and dati.ruolo != utente.ruolo)):
        raise HTTPException(400, "L'amministratore di emergenza non si può disattivare né cambiare ruolo")

    modifiche = dati.model_dump(exclude_unset=True)
    if "interno" in modifiche:
        modifiche["interno"] = (modifiche["interno"] or "").strip() or None
    for campo, valore in modifiche.items():
        setattr(utente, campo, valore)
    registra(db, "utente_modificato", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio=modifiche, request=request)
    db.commit()
    return UtenteOut.da(utente)


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
    _controlla_superadmin(io, utente, None)
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra(db, "utente_sbloccato", utente=io, oggetto=f"utente:{utente.id}", request=request)
    db.commit()
    return UtenteOut.da(utente)


@router.post("/{utente_id}/password", response_model=UtenteOut)
def reimposta_password(
    utente_id: int,
    dati: ResetPassword,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    """Password provvisoria per un utente locale che l'ha dimenticata: la cambierà al prossimo accesso.

    Solo il super-admin. Per gli utenti di dominio non c'è nulla da reimpostare: la password è di Windows.
    """
    utente = db.get(Utente, utente_id)
    if utente is None:
        raise HTTPException(404, "Utente non trovato")
    _controlla_admin_globale(utente)
    if utente.origine != ORIGINE_LOCALE:
        raise HTTPException(400, "La password degli utenti di dominio si gestisce in Active Directory")
    if utente.id == io.id:
        raise HTTPException(400, "Per la tua password usa «Cambia password»")
    utente.password_hash = hash_password(dati.password)
    utente.deve_cambiare_password = True
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra(db, "password_reimpostata", utente=io, oggetto=f"utente:{utente.id}", request=request)
    db.commit()
    return UtenteOut.da(utente)
