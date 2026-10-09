"""Login (Active Directory o admin locale), sessione in cookie e controllo dei ruoli."""

import logging
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import ORIGINE_AD, ORIGINE_LOCALE, RUOLO_RESPONSABILE, Impostazione, Utente

log = logging.getLogger(__name__)

COOKIE_NAME = "crm_sessione"
PERCORSI_CAMBIO_PASSWORD = {"/api/auth/me", "/api/auth/password", "/api/auth/logout"}
PASSWORD_MIN = 10
IMPOSTAZIONE_AD = "active_directory"
_hasher = PasswordHasher()


class ADNonRaggiungibile(Exception):
    pass


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verifica_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def normalizza_username(username: str) -> str:
    """'REGIE\\mario.rossi', 'mario.rossi@regie.local' e 'Mario.Rossi' diventano 'mario.rossi'."""
    u = username.strip().lower()
    if "\\" in u:
        u = u.split("\\", 1)[1]
    if "@" in u:
        u = u.split("@", 1)[0]
    return u


@dataclass
class ConfigAD:
    server: str = ""
    porta: int = 636
    ssl: bool = True
    dominio: str = ""  # es. regieauto.local, usato come utente@dominio
    certificato_ca: str = ""  # certificato della CA interna in formato PEM
    file_ca: str = ""  # in alternativa, percorso del certificato sul server (AD_CA_FILE)
    origine: str = "nessuna"  # pagina / file / nessuna

    @property
    def configurato(self) -> bool:
        return bool(self.server and self.dominio)


def config_ad(db: Session | None = None) -> ConfigAD:
    """Impostazioni dell'Active Directory: quelle salvate dalla pagina del CRM, altrimenti il file .env."""
    if db is None:
        with SessionLocal() as nuova:
            return config_ad(nuova)
    salvata = db.get(Impostazione, IMPOSTAZIONE_AD)
    if salvata is not None:
        v = salvata.valore
        return ConfigAD(
            server=v.get("server", ""),
            porta=int(v.get("porta", 636)),
            ssl=bool(v.get("ssl", True)),
            dominio=v.get("dominio", ""),
            certificato_ca=v.get("certificato_ca", ""),
            origine="pagina",
        )
    s = get_settings()
    return ConfigAD(
        server=s.ad_server,
        porta=s.ad_port,
        ssl=s.ad_use_ssl,
        dominio=s.ad_domain,
        file_ca=s.ad_ca_file,
        origine="file" if s.ad_server else "nessuna",
    )


def verifica_ad(username: str, password: str, cfg: ConfigAD | None = None) -> bool:
    """Prova il bind sull'Active Directory con le credenziali dell'utente."""
    from ldap3 import SIMPLE, Connection, Server, Tls

    cfg = cfg or config_ad()
    timeout = get_settings().ad_timeout
    if not cfg.configurato:
        raise ADNonRaggiungibile("Active Directory non configurato")
    # Un bind con password vuota su AD riesce come "anonimo": va sempre rifiutato.
    if not password:
        return False

    tls = None
    if cfg.ssl:
        tls = Tls(
            validate=ssl.CERT_REQUIRED,
            ca_certs_file=cfg.file_ca or None,
            ca_certs_data=cfg.certificato_ca or None,
        )
    conn = None
    try:
        server = Server(cfg.server, port=cfg.porta, use_ssl=cfg.ssl, tls=tls, connect_timeout=timeout)
        conn = Connection(
            server,
            user=f"{username}@{cfg.dominio}",
            password=password,
            authentication=SIMPLE,
            receive_timeout=timeout,
            raise_exceptions=False,
        )
        ok = conn.bind()
    except Exception as exc:  # errori di rete, TLS, timeout, certificato non valido
        log.warning("AD non raggiungibile: %s", exc)
        raise ADNonRaggiungibile(str(exc)) from exc
    finally:
        try:
            if conn is not None:
                conn.unbind()
        except Exception:
            pass
    return bool(ok)


def autentica(db: Session, username: str, password: str) -> Utente | None:
    """Restituisce l'utente se le credenziali sono giuste, altrimenti None.

    Solo chi è abilitato nel CRM può entrare: AD verifica la password, il CRM decide l'accesso.
    """
    s = get_settings()
    nome = normalizza_username(username)
    utente = db.scalar(select(Utente).where(Utente.username == nome))
    if utente is None or not utente.attivo:
        return None

    adesso = datetime.now(UTC)
    if utente.bloccato_fino and utente.bloccato_fino > adesso:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Troppi tentativi falliti. Riprova tra qualche minuto.",
        )

    if utente.origine == ORIGINE_LOCALE:
        ok = verifica_password(utente.password_hash, password)
    elif utente.origine == ORIGINE_AD:
        ok = verifica_ad(nome, password)
    else:
        ok = False

    if ok:
        utente.tentativi_falliti = 0
        utente.bloccato_fino = None
        utente.ultimo_accesso = adesso
    else:
        utente.tentativi_falliti += 1
        if utente.tentativi_falliti >= s.login_max_tentativi:
            utente.bloccato_fino = adesso + timedelta(minutes=s.login_blocco_minuti)
            utente.tentativi_falliti = 0
    db.commit()
    return utente if ok else None


def crea_token(utente: Utente) -> str:
    s = get_settings()
    adesso = datetime.now(UTC)
    payload = {
        "sub": str(utente.id),
        "iat": int(adesso.timestamp()),
        "exp": int((adesso + timedelta(minutes=s.jwt_minuti)).timestamp()),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def imposta_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.jwt_minuti * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite="strict",
        path="/",
    )


def cancella_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def utente_corrente(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> Utente:
    s = get_settings()
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessione scaduta") from None

    # L'utente si rilegge a ogni richiesta: se viene disattivato esce subito.
    utente = db.get(Utente, int(payload["sub"]))
    if utente is None or not utente.attivo:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Accesso richiesto")

    # Finché non cambia la password, l'utente può solo cambiarla (o uscire).
    if utente.deve_cambiare_password and request.url.path not in PERCORSI_CAMBIO_PASSWORD:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Devi prima cambiare la password")

    # Rinnovo automatico quando è passata metà della durata della sessione.
    restante = payload["exp"] - datetime.now(UTC).timestamp()
    if restante < s.jwt_minuti * 30:
        imposta_cookie(response, crea_token(utente))
    return utente


def solo_responsabile(utente: Utente = Depends(utente_corrente)) -> Utente:
    if utente.ruolo != RUOLO_RESPONSABILE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Operazione riservata al Responsabile")
    return utente
