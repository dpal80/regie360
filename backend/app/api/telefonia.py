import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import CONTATTO_CHIUSO, Cliente, Contatto, Impostazione, Utente
from app.security import normalizza_username, solo_superadmin, utente_corrente
from app.services.telefonia import (
    IMPOSTAZIONE_NETHVOICE,
    ConfigNethVoice,
    CredenzialiRifiutate,
    NethVoiceNonRaggiungibile,
    SenzaInternoWeb,
    config_nethvoice,
    data_config,
    leggi_telefono,
    ottieni_telefono,
    salva_telefono,
    solo_cifre,
)

router = APIRouter(tags=["telefonia"])

_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$")


class NethVoiceIn(BaseModel):
    attivo: bool = True
    cti_host: str = Field(min_length=1, max_length=255)
    sip_host: str = Field(min_length=1, max_length=255)
    sip_porta: str = Field(min_length=1, max_length=5, pattern=r"^\d+$")
    certificato_ca: str = Field(default="", max_length=20000)


class StatoTelefono(BaseModel):
    attivo: bool  # la telefonia è accesa e configurata
    collegato: bool  # questo utente ha collegato il suo telefono
    interno: str | None = None
    # Dati per Phone Island: contengono la password SIP, restano solo nella memoria della pagina.
    data_config: str | None = None


class CollegaIn(BaseModel):
    username: str | None = Field(default=None, max_length=150)
    password: str = Field(min_length=1, max_length=256)


def _host(valore: str, cosa: str) -> str:
    valore = valore.strip().lower().removeprefix("https://").rstrip("/")
    if not _HOST.match(valore):
        raise HTTPException(422, f"{cosa}: scrivi solo il nome del server, es. cti.regieauto.local")
    return valore


def _stato(cfg: ConfigNethVoice, utente: Utente) -> StatoTelefono:
    telefono = leggi_telefono(utente) if cfg.configurato else None
    if telefono is None:
        return StatoTelefono(attivo=cfg.configurato, collegato=False)
    return StatoTelefono(
        attivo=True, collegato=True, interno=telefono["sip_interno"], data_config=data_config(cfg, telefono)
    )


@router.get("/impostazioni/nethvoice", response_model=NethVoiceIn)
def leggi_nethvoice(db: Session = Depends(get_db), _: Utente = Depends(solo_superadmin)):
    cfg = config_nethvoice(db)
    return NethVoiceIn.model_construct(
        attivo=cfg.attivo, cti_host=cfg.cti_host, sip_host=cfg.sip_host, sip_porta=cfg.sip_porta,
        certificato_ca=cfg.certificato_ca,
    )


@router.put("/impostazioni/nethvoice", response_model=NethVoiceIn)
def salva_nethvoice(
    dati: NethVoiceIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    certificato = dati.certificato_ca.strip()
    if certificato and "BEGIN CERTIFICATE" not in certificato:
        raise HTTPException(422, "Il certificato deve essere in formato PEM (inizia con -----BEGIN CERTIFICATE-----)")
    valore = {
        "attivo": dati.attivo,
        "cti_host": _host(dati.cti_host, "Server CTI"),
        "sip_host": _host(dati.sip_host, "Server SIP"),
        "sip_porta": dati.sip_porta,
        "certificato_ca": certificato,
    }
    salvata = db.get(Impostazione, IMPOSTAZIONE_NETHVOICE)
    if salvata is None:
        db.add(Impostazione(chiave=IMPOSTAZIONE_NETHVOICE, valore=valore))
    else:
        salvata.valore = valore
    registra(db, "nethvoice_configurato", utente=io, oggetto="impostazione:nethvoice",
             dettaglio={k: v for k, v in valore.items() if k != "certificato_ca"}, request=request)
    db.commit()
    return NethVoiceIn.model_construct(**valore)


@router.get("/telefonia/stato", response_model=StatoTelefono)
def stato(db: Session = Depends(get_db), io: Utente = Depends(utente_corrente)):
    return _stato(config_nethvoice(db), io)


@router.post("/telefonia/collega", response_model=StatoTelefono)
def collega(
    dati: CollegaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    """Collega il telefono web dell'utente: servono le sue credenziali di NethVoice, che non vengono salvate."""
    cfg = config_nethvoice(db)
    if not cfg.configurato:
        raise HTTPException(400, "La telefonia non è ancora stata configurata")
    username = normalizza_username(dati.username or io.username)
    try:
        telefono = ottieni_telefono(cfg, username, dati.password)
    except CredenzialiRifiutate:
        registra(db, "telefono_rifiutato", utente=io, dettaglio={"utente_nethvoice": username}, request=request)
        db.commit()
        raise HTTPException(400, "NethVoice ha rifiutato nome utente o password") from None
    except SenzaInternoWeb:
        raise HTTPException(400, "Su NethVoice questo utente non ha il telefono web (interno WebRTC)") from None
    except NethVoiceNonRaggiungibile as exc:
        raise HTTPException(503, f"NethVoice non risponde: {exc}") from None
    salva_telefono(io, telefono)
    registra(db, "telefono_collegato", utente=io,
             dettaglio={"utente_nethvoice": username, "interno": telefono["sip_interno"]}, request=request)
    db.commit()
    return _stato(cfg, io)


@router.delete("/telefonia/collega", response_model=StatoTelefono)
def scollega(request: Request, db: Session = Depends(get_db), io: Utente = Depends(utente_corrente)):
    io.telefono_cifrato = None
    registra(db, "telefono_scollegato", utente=io, request=request)
    db.commit()
    return _stato(config_nethvoice(db), io)


@router.get("/telefonia/cerca")
def cerca_numero(numero: str, db: Session = Depends(get_db), io: Utente = Depends(utente_corrente)):
    """Chi sta chiamando: cerca il numero tra i clienti, confrontando le ultime cifre."""
    cifre = solo_cifre(numero)
    if len(cifre) < 6:
        return {"clienti": []}
    coda = cifre[-9:]
    pulito = lambda colonna: func.regexp_replace(colonna, r"\D", "", "g")  # noqa: E731
    trovati = db.scalars(
        select(Cliente)
        .where(or_(pulito(Cliente.telefono_cellulare).like(f"%{coda}"),
                   pulito(Cliente.telefono_fisso).like(f"%{coda}")))
        .order_by(Cliente.nominativo)
        .limit(5)
    ).all()
    responsabile = io.responsabile
    clienti = []
    for c in trovati:
        miei = select(Contatto.id).where(Contatto.cliente_id == c.id)
        if not responsabile:
            miei = miei.where(Contatto.operatore_id == io.id)
        contatto_id = db.scalar(miei.order_by(Contatto.stato == CONTATTO_CHIUSO, Contatto.id.desc()).limit(1))
        clienti.append({
            "nominativo": c.nominativo,
            # La scheda completa si apre solo a chi può vederla: il Responsabile, o l'operatore col suo contatto.
            "cliente_id": c.id if responsabile else None,
            "contatto_id": contatto_id,
        })
    return {"clienti": clienti}
