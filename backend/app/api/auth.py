from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import ORIGINE_LOCALE, Utente
from app.security import (
    PASSWORD_MIN,
    ADNonRaggiungibile,
    autentica,
    cancella_cookie,
    crea_token,
    hash_password,
    imposta_cookie,
    normalizza_username,
    utente_corrente,
    verifica_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class UtenteOut(BaseModel):
    id: int
    username: str
    nome: str
    ruolo: str
    origine: str
    interno: str | None
    deve_cambiare_password: bool

    model_config = {"from_attributes": True}


class CambioPasswordIn(BaseModel):
    attuale: str
    nuova: str = Field(min_length=PASSWORD_MIN, max_length=256)


@router.post("/login", response_model=UtenteOut)
def login(dati: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    try:
        utente = autentica(db, dati.username, dati.password)
    except ADNonRaggiungibile:
        registra(db, "login_ad_non_raggiungibile", username=normalizza_username(dati.username), request=request)
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Il server di dominio non risponde. Riprova tra poco o contatta l'amministratore.",
        ) from None
    if utente is None:
        registra(db, "login_fallito", username=normalizza_username(dati.username), request=request)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nome utente o password non corretti")

    imposta_cookie(response, crea_token(utente))
    registra(db, "login", utente=utente, request=request)
    db.commit()
    return utente


@router.post("/logout", status_code=204)
def logout(response: Response):
    cancella_cookie(response)


@router.get("/me", response_model=UtenteOut)
def me(utente: Utente = Depends(utente_corrente)):
    return utente


@router.post("/password", status_code=204)
def cambia_password(
    dati: CambioPasswordIn,
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: Session = Depends(get_db),
):
    """Solo per gli utenti locali: quelli di dominio cambiano la password in Windows."""
    if utente.origine != ORIGINE_LOCALE:
        raise HTTPException(400, "La password degli utenti di dominio si cambia da Windows")
    if not verifica_password(utente.password_hash, dati.attuale):
        raise HTTPException(400, "La password attuale non è corretta")
    if dati.nuova == dati.attuale:
        raise HTTPException(400, "La nuova password deve essere diversa da quella attuale")
    utente.password_hash = hash_password(dati.nuova)
    utente.deve_cambiare_password = False
    registra(db, "cambio_password", utente=utente, request=request)
    db.commit()
