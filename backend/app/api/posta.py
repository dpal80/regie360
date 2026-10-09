import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import get_db
from app.models import Impostazione, Utente
from app.security import solo_superadmin
from app.segreti import cifra
from app.services.posta import (
    IMPOSTAZIONE_M365,
    PostaNonConfigurata,
    PostaNonInviata,
    config_posta,
    invia_mail,
)

router = APIRouter(prefix="/impostazioni/microsoft365", tags=["posta"])

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
_DOMINIO = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$")


class PostaIn(BaseModel):
    attivo: bool = True
    tenant_id: str = Field(min_length=1, max_length=255)
    client_id: str = Field(min_length=1, max_length=64)
    mittente: str = Field(min_length=3, max_length=254)
    # Vuoto = resta il segreto già salvato. Il CRM non lo mostra mai più.
    segreto: str = Field(default="", max_length=500)


class PostaOut(BaseModel):
    attivo: bool
    tenant_id: str
    client_id: str
    mittente: str
    segreto_presente: bool


class ProvaIn(BaseModel):
    destinatario: str = Field(min_length=3, max_length=254)


def _out(db: Session) -> PostaOut:
    cfg = config_posta(db)
    return PostaOut(attivo=cfg.attivo, tenant_id=cfg.tenant_id, client_id=cfg.client_id,
                    mittente=cfg.mittente, segreto_presente=bool(cfg.segreto))


@router.get("", response_model=PostaOut)
def leggi(db: Session = Depends(get_db), _: Utente = Depends(solo_superadmin)):
    return _out(db)


@router.put("", response_model=PostaOut)
def salva(
    dati: PostaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    tenant = dati.tenant_id.strip()
    if not (_GUID.match(tenant) or _DOMINIO.match(tenant)):
        raise HTTPException(422, "ID tenant non valido: è l'ID della directory in Entra ID, o il dominio (es. regieauto.onmicrosoft.com)")
    cliente = dati.client_id.strip()
    if not _GUID.match(cliente):
        raise HTTPException(422, "ID applicazione non valido: è l'«ID applicazione (client)» dell'app in Entra ID")
    mittente = dati.mittente.strip().lower()
    if not _EMAIL.match(mittente):
        raise HTTPException(422, "Il mittente deve essere l'indirizzo di una casella di Microsoft 365")
    salvata = db.get(Impostazione, IMPOSTAZIONE_M365)
    segreto_cifrato = cifra(dati.segreto) if dati.segreto else (salvata.valore.get("segreto_cifrato") if salvata else None)
    if not segreto_cifrato:
        raise HTTPException(422, "Inserisci il segreto dell'applicazione")
    valore = {"attivo": dati.attivo, "tenant_id": tenant, "client_id": cliente, "mittente": mittente,
              "segreto_cifrato": segreto_cifrato}
    if salvata is None:
        db.add(Impostazione(chiave=IMPOSTAZIONE_M365, valore=valore))
    else:
        salvata.valore = valore
    registra(db, "microsoft365_configurato", utente=io, oggetto="impostazione:microsoft365",
             dettaglio={"tenant_id": tenant, "client_id": cliente, "mittente": mittente, "attivo": dati.attivo,
                        "segreto_cambiato": bool(dati.segreto)}, request=request)
    db.commit()
    return _out(db)


@router.post("/prova")
def prova(
    dati: ProvaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_superadmin),
):
    """Spedisce un'e-mail di prova con le impostazioni salvate."""
    destinatario = dati.destinatario.strip()
    if not _EMAIL.match(destinatario):
        raise HTTPException(422, "Indirizzo del destinatario non valido")
    registra(db, "mail_di_prova", utente=io, oggetto="impostazione:microsoft365",
             dettaglio={"destinatario": destinatario}, request=request)
    db.commit()
    try:
        invia_mail(
            config_posta(db), [destinatario], "Regie360: e-mail di prova",
            f"Questa e-mail conferma che Regie360 riesce a spedire con Microsoft 365.\n\nRichiesta da {io.nome}.",
        )
    except PostaNonConfigurata:
        return {"ok": False, "messaggio": "Salva prima le impostazioni, con la posta attiva."}
    except PostaNonInviata as exc:
        return {"ok": False, "messaggio": str(exc)}
    return {"ok": True, "messaggio": f"E-mail di prova spedita a {destinatario}."}
