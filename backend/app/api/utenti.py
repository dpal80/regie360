from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import ORIGINE_AD, ORIGINE_LOCALE, RUOLI, RUOLO_SUPERADMIN, Utente
from app.config import get_settings
from app.services import duefattori
from app.services.posta import (
    PostaNonConfigurata,
    PostaNonInviata,
    config_posta,
    invia_credenziali,
    invia_nuova_password,
)
from app.security import (
    EMAIL,
    PASSWORD_MIN,
    genera_password,
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
    email: str | None
    attivo: bool
    deve_cambiare_password: bool
    totp_attivo: bool
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
    email: str | None = Field(default=None, max_length=254)
    # Solo per gli utenti locali: password provvisoria, da cambiare al primo accesso.
    password: str | None = Field(default=None, max_length=256)
    # Utenti locali: la password la sceglie il CRM e arriva all'utente per e-mail, senza passare da nessuno.
    invia_credenziali: bool = False


class ResetPassword(BaseModel):
    password: str | None = Field(default=None, min_length=PASSWORD_MIN, max_length=256)
    # La nuova password la sceglie il CRM e arriva all'utente per e-mail.
    invia: bool = False


class UtenteModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    ruolo: str | None = None
    interno: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=254)
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


def _email(valore: str | None) -> str | None:
    email = (valore or "").strip().lower()
    if email and not EMAIL.match(email):
        raise HTTPException(422, "Indirizzo e-mail non valido")
    return email or None


def _non_inviata(exc: Exception) -> HTTPException:
    if isinstance(exc, PostaNonConfigurata):
        return HTTPException(400, "L'invio delle e-mail non è configurato: vedi Impostazioni › Microsoft 365")
    return HTTPException(502, f"E-mail non inviata, nulla è stato cambiato. {exc}")


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
    email = _email(dati.email)
    password_hash = None
    provvisoria = None
    if dati.origine == ORIGINE_LOCALE:
        if dati.invia_credenziali and not email:
            raise HTTPException(422, "Per inviare le credenziali serve l'e-mail dell'utente")
        provvisoria = genera_password() if dati.invia_credenziali else _controlla_password(dati.password)
        password_hash = hash_password(provvisoria)
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
        email=email,
        attivo=True,
    )
    db.add(utente)
    db.flush()
    if dati.origine == ORIGINE_LOCALE and dati.invia_credenziali:
        try:
            invia_credenziali(config_posta(db), email, utente.nome, username, provvisoria)
        except (PostaNonConfigurata, PostaNonInviata) as exc:
            db.rollback()
            raise _non_inviata(exc) from None
    registra(db, "utente_creato", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio={"username": username, "ruolo": dati.ruolo, "origine": dati.origine,
                        "credenziali_per_email": dati.invia_credenziali},
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
    if "email" in modifiche:
        # All'e-mail arrivano i codici per reimpostare la password: la cambia solo chi può già reimpostarla.
        if not io.superadmin:
            raise HTTPException(403, "L'e-mail di un utente la cambia solo un super-admin")
        modifiche["email"] = _email(modifiche["email"])
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
    if dati.invia:
        if not utente.email:
            raise HTTPException(422, "Questo utente non ha un'e-mail")
        nuova = genera_password()
        try:
            invia_nuova_password(config_posta(db), utente.email, utente.nome, utente.username, nuova)
        except (PostaNonConfigurata, PostaNonInviata) as exc:
            raise _non_inviata(exc) from None
    else:
        nuova = _controlla_password(dati.password)
    utente.password_hash = hash_password(nuova)
    utente.deve_cambiare_password = True
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra(db, "password_reimpostata", utente=io, oggetto=f"utente:{utente.id}",
             dettaglio={"per_email": dati.invia}, request=request)
    db.commit()
    return UtenteOut.da(utente)


@router.post("/{utente_id}/2fa/azzera", response_model=UtenteOut)
def azzera_2fa(
    utente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    """Toglie la verifica in due passaggi a chi ha perso il telefono: potrà riattivarla dal suo account."""
    utente = db.get(Utente, utente_id)
    if utente is None:
        raise HTTPException(404, "Utente non trovato")
    _controlla_admin_globale(utente)
    duefattori.azzera(utente)
    registra(db, "2fa_azzerata", utente=io, oggetto=f"utente:{utente.id}", request=request)
    db.commit()
    return UtenteOut.da(utente)
