from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import Impostazione, Utente
from app.security import (
    IMPOSTAZIONE_AD,
    MAX_UTENTI_AD,
    ADNonRaggiungibile,
    ConfigAD,
    cerca_utenti_ad,
    config_ad,
    normalizza_username,
    solo_responsabile,
    solo_superadmin,
    verifica_ad,
)

router = APIRouter(prefix="/impostazioni", tags=["impostazioni"])


class ADIn(BaseModel):
    server: str = Field(min_length=1, max_length=255)
    porta: int = Field(default=636, ge=1, le=65535)
    ssl: bool = True
    dominio: str = Field(min_length=1, max_length=255)
    certificato_ca: str = Field(default="", max_length=20000)
    # Da dove si sfogliano gli utenti, es. OU=CRM,DC=regieauto,DC=local. Vuoto = tutto il dominio.
    base_dn: str = Field(default="", max_length=500)


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
    base_dn = dati.base_dn.strip()
    if base_dn and "=" not in base_dn:
        raise HTTPException(422, "La Base DN deve avere la forma OU=Operatori,DC=regieauto,DC=local")
    return ConfigAD(
        server=dati.server.strip(),
        porta=dati.porta,
        ssl=dati.ssl,
        dominio=dati.dominio.strip().lower(),
        certificato_ca=certificato,
        base_dn=base_dn,
        origine="pagina",
    )


def _out(cfg: ConfigAD) -> ADOut:
    return ADOut(
        server=cfg.server, porta=cfg.porta, ssl=cfg.ssl, dominio=cfg.dominio,
        certificato_ca=cfg.certificato_ca, base_dn=cfg.base_dn, origine=cfg.origine,
    )


@router.get("/ad", response_model=ADOut)
def leggi_ad(db: Session = Depends(get_db), _: Utente = Depends(solo_superadmin)):
    return _out(config_ad(db))


@router.put("/ad", response_model=ADOut)
def salva_ad(
    dati: ADIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    cfg = _pulisci(dati)
    valore = {
        "server": cfg.server, "porta": cfg.porta, "ssl": cfg.ssl,
        "dominio": cfg.dominio, "certificato_ca": cfg.certificato_ca, "base_dn": cfg.base_dn,
    }
    salvata = db.get(Impostazione, IMPOSTAZIONE_AD)
    if salvata is None:
        db.add(Impostazione(chiave=IMPOSTAZIONE_AD, valore=valore))
    else:
        salvata.valore = valore
    registra(db, "ad_configurato", utente=io, oggetto="impostazione:active_directory",
             dettaglio={"server": cfg.server, "porta": cfg.porta, "ssl": cfg.ssl, "dominio": cfg.dominio,
                        "base_dn": cfg.base_dn},
             request=request)
    db.commit()
    return _out(cfg)


@router.delete("/ad", response_model=ADOut)
def rimuovi_ad(request: Request, db: Session = Depends(get_db), io: Utente = Depends(solo_superadmin)):
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
    io: Utente = Depends(solo_superadmin),
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


class SfogliaIn(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)
    q: str = Field(default="", max_length=100)


class UtenteAD(BaseModel):
    username: str
    nome: str
    email: str | None
    reparto: str | None
    gia_nel_crm: bool


class SfogliaOut(BaseModel):
    base_dn: str
    utenti: list[UtenteAD]
    troppi: bool  # l'elenco è stato tagliato: conviene restringere la ricerca


@router.post("/ad/utenti", response_model=SfogliaOut)
def sfoglia_ad(
    dati: SfogliaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Elenca gli utenti di dominio sotto la Base DN, per sceglierli invece di scriverne il nome a mano.

    Il CRM non conserva un account di servizio: entra in AD con le credenziali di chi sfoglia.
    """
    cfg = config_ad(db)
    registra(db, "ad_sfogliato", utente=io, oggetto="impostazione:active_directory",
             dettaglio={"base_dn": cfg.base_ricerca, "q": dati.q}, request=request)
    db.commit()
    try:
        trovati = cerca_utenti_ad(cfg, normalizza_username(dati.username), dati.password, dati.q)
    except ADNonRaggiungibile as exc:
        raise HTTPException(503, f"Active Directory non risponde: {exc}") from None
    if trovati is None:
        raise HTTPException(400, "Il server di dominio ha rifiutato nome utente o password")
    presenti = set(db.scalars(select(Utente.username)))
    return SfogliaOut(
        base_dn=cfg.base_ricerca,
        utenti=[UtenteAD(**u, gia_nel_crm=u["username"] in presenti) for u in trovati],
        troppi=len(trovati) >= MAX_UTENTI_AD,
    )
