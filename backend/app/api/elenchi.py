from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.audit import registra
from app.db import SessionLocal, get_db
from app.models import (
    EFFETTI_ESITO,
    EFFETTI_FASE,
    ELENCHI,
    ELENCO_ESITO,
    ELENCO_FASE,
    ELENCO_MOTIVO_PERDITA,
    ELENCO_MOTIVO_RICHIAMO,
    ELENCO_PRODOTTO,
    ESITO_CHIUSO,
    ESITO_ESCLUSO,
    ESITO_RICHIAMO,
    FASE_APERTA,
    FASE_PERSA,
    FASE_VINTA,
    Utente,
    VoceElenco,
)
from app.security import solo_responsabile, utente_corrente

router = APIRouter(prefix="/elenchi", tags=["elenchi"])

EFFETTI = {ELENCO_ESITO: EFFETTI_ESITO, ELENCO_FASE: EFFETTI_FASE}

# Voci di partenza: il Responsabile può rinominarle, disattivarle o aggiungerne.
PREDEFINITI = {
    ELENCO_ESITO: [
        ("Appuntamento preso", ESITO_CHIUSO),
        ("Non risponde", ESITO_RICHIAMO),
        ("Da richiamare", ESITO_RICHIAMO),
        ("Non interessato", ESITO_CHIUSO),
        ("Numero errato", ESITO_CHIUSO),
        ("Non vuole essere richiamato", ESITO_ESCLUSO),
    ],
    ELENCO_MOTIVO_RICHIAMO: [
        ("Tagliando", None), ("Revisione", None), ("Fine garanzia", None), ("Cambio auto", None),
    ],
    ELENCO_FASE: [
        ("Appuntamento preso", FASE_APERTA), ("Chiusa vinta", FASE_VINTA), ("Chiusa persa", FASE_PERSA),
    ],
    ELENCO_MOTIVO_PERDITA: [
        ("Non si è presentato", None), ("Ha scelto un'altra officina", None), ("Prezzo", None), ("Altro", None),
    ],
    ELENCO_PRODOTTO: [],
}


def crea_elenchi_predefiniti() -> None:
    """Al primo avvio riempie gli elenchi ancora vuoti (mai toccati) con le voci di partenza."""
    with SessionLocal() as db:
        for elenco, voci in PREDEFINITI.items():
            if not voci or db.scalar(select(func.count(VoceElenco.id)).where(VoceElenco.elenco == elenco)):
                continue
            db.execute(
                insert(VoceElenco)
                .values([
                    {"elenco": elenco, "nome": nome, "effetto": effetto, "ordine": i, "attivo": True}
                    for i, (nome, effetto) in enumerate(voci)
                ])
                .on_conflict_do_nothing(index_elements=["elenco", "nome"])
            )
        db.commit()


class VoceOut(BaseModel):
    id: int
    elenco: str
    nome: str
    effetto: str | None
    famiglia: str | None
    ordine: int
    attivo: bool

    model_config = {"from_attributes": True}


class VoceNuova(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    effetto: str | None = None
    famiglia: str | None = Field(default=None, max_length=200)


class VoceModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    effetto: str | None = None
    famiglia: str | None = Field(default=None, max_length=200)
    attivo: bool | None = None


def _controlla_elenco(elenco: str) -> None:
    if elenco not in ELENCHI:
        raise HTTPException(404, "Elenco non trovato")


def _controlla_effetto(elenco: str, effetto: str | None) -> str | None:
    ammessi = EFFETTI.get(elenco)
    if ammessi is None:
        return None
    if effetto not in ammessi:
        raise HTTPException(422, "Scegli cosa succede con questa voce")
    return effetto


def _nome_libero(db: Session, elenco: str, nome: str, escluso: int | None = None) -> str:
    nome = nome.strip()
    altra = db.scalar(select(VoceElenco).where(VoceElenco.elenco == elenco, VoceElenco.nome == nome))
    if altra is not None and altra.id != escluso:
        raise HTTPException(409, "Questa voce c'è già")
    return nome


@router.get("/{elenco}", response_model=list[VoceOut])
def voci(
    elenco: str,
    tutte: bool = False,
    db: Session = Depends(get_db),
    _: Utente = Depends(utente_corrente),
):
    _controlla_elenco(elenco)
    query = select(VoceElenco).where(VoceElenco.elenco == elenco)
    if not tutte:
        query = query.where(VoceElenco.attivo)
    return db.scalars(query.order_by(VoceElenco.ordine, VoceElenco.id)).all()


@router.post("/{elenco}", response_model=VoceOut, status_code=201)
def aggiungi(
    elenco: str,
    dati: VoceNuova,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    _controlla_elenco(elenco)
    ultimo = db.scalar(select(func.max(VoceElenco.ordine)).where(VoceElenco.elenco == elenco))
    voce = VoceElenco(
        elenco=elenco,
        nome=_nome_libero(db, elenco, dati.nome),
        effetto=_controlla_effetto(elenco, dati.effetto),
        famiglia=(dati.famiglia or "").strip() or None if elenco == ELENCO_PRODOTTO else None,
        ordine=(ultimo if ultimo is not None else -1) + 1,
        attivo=True,
    )
    db.add(voce)
    db.flush()
    registra(db, "voce_elenco_creata", utente=io, oggetto=f"{elenco}:{voce.id}",
             dettaglio={"nome": voce.nome}, request=request)
    db.commit()
    return voce


@router.patch("/voci/{voce_id}", response_model=VoceOut)
def modifica(
    voce_id: int,
    dati: VoceModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    voce = db.get(VoceElenco, voce_id)
    if voce is None:
        raise HTTPException(404, "Voce non trovata")
    modifiche = dati.model_dump(exclude_unset=True)
    if "nome" in modifiche:
        voce.nome = _nome_libero(db, voce.elenco, dati.nome, escluso=voce.id)
    if "effetto" in modifiche:
        voce.effetto = _controlla_effetto(voce.elenco, dati.effetto)
    if "famiglia" in modifiche and voce.elenco == ELENCO_PRODOTTO:
        voce.famiglia = (dati.famiglia or "").strip() or None
    if dati.attivo is not None:
        voce.attivo = dati.attivo
    registra(db, "voce_elenco_modificata", utente=io, oggetto=f"{voce.elenco}:{voce.id}",
             dettaglio=modifiche, request=request)
    db.commit()
    return voce
