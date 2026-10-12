import logging
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import ORIGINE_AD, ORIGINE_LOCALE, Utente
from app.security import (
    EMAIL,
    PASSWORD_MIN,
    ADNonRaggiungibile,
    autentica,
    cancella_cookie,
    conta_tentativo_fallito,
    crea_token,
    hash_password,
    imposta_cookie,
    normalizza_username,
    utente_corrente,
    verifica_password,
)
from app.services import duefattori
from app.services.posta import PostaNonInviata, config_posta, invia_codice_reset
from app.services.telefonia import collega_al_login

log = logging.getLogger(__name__)

RESET_MINUTI = 15
RESET_TENTATIVI = 5
RESET_ATTESA = timedelta(minutes=2)  # tra una richiesta di codice e la successiva

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)
    # Codice dell'app di autenticazione, per chi ha attivato la verifica in due passaggi.
    codice: str | None = Field(default=None, max_length=20)


class UtenteOut(BaseModel):
    id: int
    username: str
    nome: str
    ruolo: str
    origine: str
    interno: str | None
    email: str | None
    deve_cambiare_password: bool
    totp_attivo: bool

    model_config = {"from_attributes": True}


class CodiceIn(BaseModel):
    codice: str = Field(min_length=6, max_length=20)


class EmailIn(BaseModel):
    email: str = Field(default="", max_length=254)
    # Per gli utenti locali serve la password: chi trova una sessione aperta non deve poter
    # cambiare l'indirizzo e poi farsi mandare il codice di reset.
    password: str | None = Field(default=None, max_length=256)


class DimenticataIn(BaseModel):
    username: str = Field(min_length=1, max_length=150)


class ReimpostaIn(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    codice: str = Field(min_length=1, max_length=20)
    nuova: str = Field(min_length=PASSWORD_MIN, max_length=256)


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

    if utente.totp_attivo:
        if not dati.codice:
            # La password è giusta: la pagina di accesso chiede il secondo passaggio.
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, {
                "codice_richiesto": True, "messaggio": "Inserisci il codice della tua app di autenticazione"})
        if not duefattori.verifica(utente, dati.codice):
            conta_tentativo_fallito(utente)
            registra(db, "login_codice_sbagliato", utente=utente, request=request)
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, {
                "codice_richiesto": True, "messaggio": "Codice non corretto"})
        utente.tentativi_falliti = 0
    if utente.origine == ORIGINE_AD:
        collega_al_login(db, utente, dati.password)
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


@router.put("/email", response_model=UtenteOut)
def cambia_email(
    dati: EmailIn,
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: Session = Depends(get_db),
):
    """L'indirizzo a cui il CRM manda le credenziali e i codici per reimpostare la password."""
    email = dati.email.strip().lower()
    if email and not EMAIL.match(email):
        raise HTTPException(422, "Indirizzo e-mail non valido")
    if utente.origine == ORIGINE_LOCALE and not verifica_password(utente.password_hash, dati.password or ""):
        raise HTTPException(400, "Per cambiare l'e-mail conferma la tua password")
    utente.email = email or None
    registra(db, "email_cambiata", utente=utente, request=request)
    db.commit()
    return utente


@router.post("/2fa/avvia")
def avvia_2fa(request: Request, utente: Utente = Depends(utente_corrente), db: Session = Depends(get_db)):
    """Primo passo: il CRM dà il codice QR da inquadrare con l'app di autenticazione."""
    if utente.totp_attivo:
        raise HTTPException(400, "La verifica in due passaggi è già attiva")
    dati = duefattori.prepara(utente)
    db.commit()
    return dati


@router.post("/2fa/conferma", response_model=UtenteOut)
def conferma_2fa(
    dati: CodiceIn,
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: Session = Depends(get_db),
):
    """Secondo passo: un codice giusto dimostra che l'app è configurata, e la verifica si attiva."""
    if utente.totp_attivo:
        raise HTTPException(400, "La verifica in due passaggi è già attiva")
    if not duefattori.verifica(utente, dati.codice):
        raise HTTPException(400, "Codice non corretto: controlla che l'ora del telefono sia giusta e riprova")
    utente.totp_attivo = True
    registra(db, "2fa_attivata", utente=utente, request=request)
    db.commit()
    return utente


@router.post("/2fa/disattiva", response_model=UtenteOut)
def disattiva_2fa(
    dati: CodiceIn,
    request: Request,
    utente: Utente = Depends(utente_corrente),
    db: Session = Depends(get_db),
):
    if not utente.totp_attivo:
        raise HTTPException(400, "La verifica in due passaggi non è attiva")
    if not duefattori.verifica(utente, dati.codice):
        raise HTTPException(400, "Codice non corretto")
    duefattori.azzera(utente)
    registra(db, "2fa_disattivata", utente=utente, request=request)
    db.commit()
    return utente


@router.get("/opzioni")
def opzioni(db: Session = Depends(get_db)):
    """Cosa mostrare nella pagina di accesso: il reset della password serve la posta configurata."""
    return {"reset_password": config_posta(db).configurato}


@router.post("/password-dimenticata", status_code=204)
def password_dimenticata(dati: DimenticataIn, request: Request, db: Session = Depends(get_db)):
    """Manda per e-mail un codice usa e getta. Risponde sempre allo stesso modo, che l'utente esista o no."""
    cfg = config_posta(db)
    username = normalizza_username(dati.username)
    utente = db.scalar(select(Utente).where(Utente.username == username))
    adesso = datetime.now(UTC)
    if (
        not cfg.configurato
        or utente is None
        or not utente.attivo
        or utente.origine != ORIGINE_LOCALE
        or not utente.email
        or (utente.reset_richiesto_il and adesso - utente.reset_richiesto_il < RESET_ATTESA)
    ):
        registra(db, "reset_password_non_inviato", username=username, request=request)
        db.commit()
        return
    codice = f"{secrets.randbelow(10**8):08d}"
    utente.reset_codice_hash = hash_password(codice)
    utente.reset_scadenza = adesso + timedelta(minutes=RESET_MINUTI)
    utente.reset_tentativi = 0
    utente.reset_richiesto_il = adesso
    registra(db, "reset_password_richiesto", utente=utente, request=request)
    db.commit()
    try:
        invia_codice_reset(cfg, utente.email, utente.nome, codice, RESET_MINUTI)
    except PostaNonInviata as exc:
        log.warning("Codice di reset non inviato a %s: %s", username, exc)


@router.post("/password-reimposta", status_code=204)
def password_reimposta(dati: ReimpostaIn, request: Request, db: Session = Depends(get_db)):
    """Sceglie una nuova password con il codice ricevuto per e-mail. La verifica in due passaggi resta attiva."""
    username = normalizza_username(dati.username)
    utente = db.scalar(select(Utente).where(Utente.username == username))
    rifiuto = HTTPException(400, "Codice non valido o scaduto: richiedine uno nuovo")
    adesso = datetime.now(UTC)
    if (
        utente is None
        or not utente.attivo
        or utente.origine != ORIGINE_LOCALE
        or not utente.reset_codice_hash
        or not utente.reset_scadenza
        or utente.reset_scadenza < adesso
    ):
        raise rifiuto
    cifre = "".join(c for c in dati.codice if c.isdigit())
    if not verifica_password(utente.reset_codice_hash, cifre):
        utente.reset_tentativi += 1
        if utente.reset_tentativi >= RESET_TENTATIVI:
            utente.reset_codice_hash = None
        registra(db, "reset_password_codice_sbagliato", utente=utente, request=request)
        db.commit()
        raise rifiuto
    utente.password_hash = hash_password(dati.nuova)
    utente.deve_cambiare_password = False
    utente.reset_codice_hash = None
    utente.reset_scadenza = None
    utente.tentativi_falliti = 0
    utente.bloccato_fino = None
    registra(db, "reset_password_completato", utente=utente, request=request)
    db.commit()
