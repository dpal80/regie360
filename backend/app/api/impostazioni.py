from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import Impostazione, Utente
from app.security import (
    IMPOSTAZIONE_AD,
    ADNonRaggiungibile,
    ConfigAD,
    config_ad,
    normalizza_username,
    solo_responsabile,
    verifica_ad,
)

router = APIRouter(prefix="/impostazioni", tags=["impostazioni"])


class ADIn(BaseModel):
    server: str = Field(min_length=1, max_length=255)
    porta: int = Field(default=636, ge=1, le=65535)
    ssl: bool = True
    dominio: str = Field(min_length=1, max_length=255)
    certificato_ca: str = Field(default="", max_length=20000)


class ADOut(ADIn):
    server: str
    dominio: str
    # pagina = salvata da qui; file = letta dal file .env del server; nessuna = non configurato
    origine: str


class ProvaIn(ADIn):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class ProvaOut(BaseModel):
    ok: bool
    messaggio: str


def _pulisci(dati: ADIn) -> ConfigAD:
    certificato = dati.certificato_ca.strip()
    if certificato and "BEGIN CERTIFICATE" not in certificato:
        raise HTTPException(422, "Il certificato deve essere in formato PEM (inizia con -----BEGIN CERTIFICATE-----)")
    return ConfigAD(
        server=dati.server.strip(),
        porta=dati.porta,
        ssl=dati.ssl,
        dominio=dati.dominio.strip().lower(),
        certificato_ca=certificato,
        origine="pagina",
    )


def _out(cfg: ConfigAD) -> ADOut:
    return ADOut(
        server=cfg.server, porta=cfg.porta, ssl=cfg.ssl, dominio=cfg.dominio,
        certificato_ca=cfg.certificato_ca, origine=cfg.origine,
    )


@router.get("/ad", response_model=ADOut)
def leggi_ad(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return _out(config_ad(db))


@router.put("/ad", response_model=ADOut)
def salva_ad(
    dati: ADIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    cfg = _pulisci(dati)
    valore = {
        "server": cfg.server, "porta": cfg.porta, "ssl": cfg.ssl,
        "dominio": cfg.dominio, "certificato_ca": cfg.certificato_ca,
    }
    salvata = db.get(Impostazione, IMPOSTAZIONE_AD)
    if salvata is None:
        db.add(Impostazione(chiave=IMPOSTAZIONE_AD, valore=valore))
    else:
        salvata.valore = valore
    registra(db, "ad_configurato", utente=io, oggetto="impostazione:active_directory",
             dettaglio={"server": cfg.server, "porta": cfg.porta, "ssl": cfg.ssl, "dominio": cfg.dominio},
             request=request)
    db.commit()
    return _out(cfg)


@router.delete("/ad", response_model=ADOut)
def rimuovi_ad(request: Request, db: Session = Depends(get_db), io: Utente = Depends(solo_responsabile)):
    """Toglie le impostazioni salvate dalla pagina: tornano a valere quelle del file .env, se ci sono."""
    salvata = db.get(Impostazione, IMPOSTAZIONE_AD)
    if salvata is not None:
        db.delete(salvata)
        registra(db, "ad_rimosso", utente=io, oggetto="impostazione:active_directory", request=request)
        db.commit()
    return _out(config_ad(db))


@router.post("/ad/prova", response_model=ProvaOut)
def prova_ad(
    dati: ProvaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Prova il collegamento con i dati del modulo, prima di salvarli, usando un utente di dominio."""
    cfg = _pulisci(dati)
    registra(db, "ad_provato", utente=io, oggetto="impostazione:active_directory",
             dettaglio={"server": cfg.server, "porta": cfg.porta, "dominio": cfg.dominio}, request=request)
    db.commit()
    try:
        ok = verifica_ad(normalizza_username(dati.username), dati.password, cfg)
    except ADNonRaggiungibile as exc:
        return ProvaOut(ok=False, messaggio=f"Il server non risponde o il certificato non è valido: {exc}")
    if ok:
        return ProvaOut(ok=True, messaggio="Collegamento riuscito: il server ha accettato nome utente e password.")
    return ProvaOut(ok=False, messaggio="Il server risponde, ma ha rifiutato nome utente o password.")
