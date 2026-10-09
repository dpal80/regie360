from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.audit import registra
from app.db import get_db
from app.models import (
    ELENCO_FASE,
    ELENCO_MOTIVO_PERDITA,
    ELENCO_PRODOTTO,
    FASE_APERTA,
    FASE_PERSA,
    RUOLO_RESPONSABILE,
    Chiamata,
    Cliente,
    Opportunita,
    OpportunitaFase,
    Sede,
    Utente,
    Veicolo,
    VoceElenco,
)
from app.security import utente_corrente
from app.services.campagne import vede_cliente

router = APIRouter(prefix="/opportunita", tags=["opportunita"])

Importo = Decimal | None


class OpportunitaNuova(BaseModel):
    cliente_id: int
    veicolo_id: int | None = None
    chiamata_id: int | None = None
    fase_id: int | None = None  # vuoto = prima fase aperta dell'elenco
    data_appuntamento: datetime | None = None
    sede_id: int | None = None
    descrizione: str | None = Field(default=None, max_length=5000)
    ammontare: Importo = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    vendita_aggiuntiva: bool = False
    prezzo_vendita: Importo = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    prodotto_id: int | None = None


class OpportunitaModifica(BaseModel):
    fase_id: int | None = None
    data_appuntamento: datetime | None = None
    sede_id: int | None = None
    descrizione: str | None = Field(default=None, max_length=5000)
    ammontare: Importo = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    vendita_aggiuntiva: bool | None = None
    prezzo_vendita: Importo = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    prodotto_id: int | None = None
    motivo_perdita_id: int | None = None
    note_perdita: str | None = Field(default=None, max_length=5000)


class OpportunitaOut(BaseModel):
    id: int
    titolare: str
    cliente_id: int
    cliente: str
    telefono: str | None
    veicolo: str | None
    targa: str | None
    fase_id: int
    fase: str
    fase_effetto: str | None
    data_appuntamento: datetime | None
    sede_id: int | None
    sede: str | None
    descrizione: str | None
    ammontare: float | None
    vendita_aggiuntiva: bool
    prezzo_vendita: float | None
    prodotto_id: int | None
    prodotto: str | None
    motivo_perdita_id: int | None
    motivo_perdita: str | None
    note_perdita: str | None
    creato_il: datetime


class Pagina(BaseModel):
    totale: int
    pagina: int
    per_pagina: int
    elementi: list[OpportunitaOut]


_CARICA = (
    selectinload(Opportunita.titolare), selectinload(Opportunita.cliente), selectinload(Opportunita.veicolo),
    selectinload(Opportunita.sede), selectinload(Opportunita.fase), selectinload(Opportunita.prodotto),
    selectinload(Opportunita.motivo_perdita),
)


def _out(o: Opportunita) -> OpportunitaOut:
    v = o.veicolo
    return OpportunitaOut(
        id=o.id, titolare=o.titolare.nome, cliente_id=o.cliente_id, cliente=o.cliente.nominativo,
        telefono=o.cliente.telefono_cellulare or o.cliente.telefono_fisso,
        veicolo=" ".join(x for x in (v.marca, v.modello) if x) if v else None, targa=v.targa if v else None,
        fase_id=o.fase_id, fase=o.fase.nome, fase_effetto=o.fase.effetto,
        data_appuntamento=o.data_appuntamento, sede_id=o.sede_id, sede=o.sede.nome if o.sede else None,
        descrizione=o.descrizione, ammontare=o.ammontare, vendita_aggiuntiva=o.vendita_aggiuntiva,
        prezzo_vendita=o.prezzo_vendita, prodotto_id=o.prodotto_id,
        prodotto=o.prodotto.nome if o.prodotto else None, motivo_perdita_id=o.motivo_perdita_id,
        motivo_perdita=o.motivo_perdita.nome if o.motivo_perdita else None, note_perdita=o.note_perdita,
        creato_il=o.creato_il,
    )


def _voce(db: Session, voce_id: int | None, elenco: str, cosa: str) -> VoceElenco | None:
    if voce_id is None:
        return None
    voce = db.get(VoceElenco, voce_id)
    if voce is None or voce.elenco != elenco:
        raise HTTPException(422, f"{cosa} non valido")
    return voce


def _controlla_sede(db: Session, sede_id: int | None) -> None:
    if sede_id is not None and db.get(Sede, sede_id) is None:
        raise HTTPException(422, "Sede non valida")


def _rileggi(db: Session, opportunita_id: int) -> Opportunita:
    return db.scalar(select(Opportunita).where(Opportunita.id == opportunita_id).options(*_CARICA))


@router.get("", response_model=Pagina)
def elenco(
    fase_id: int | None = None,
    pagina: int = Query(1, ge=1),
    per_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    """Il Responsabile vede tutte le opportunità, l'operatore solo le sue."""
    query = select(Opportunita)
    if io.ruolo != RUOLO_RESPONSABILE:
        query = query.where(Opportunita.titolare_id == io.id)
    if fase_id:
        query = query.where(Opportunita.fase_id == fase_id)
    totale = db.scalar(select(func.count()).select_from(query.subquery()))
    righe = db.scalars(
        query.options(*_CARICA)
        .order_by(Opportunita.data_appuntamento.desc().nulls_last(), Opportunita.id.desc())
        .offset((pagina - 1) * per_pagina)
        .limit(per_pagina)
    ).all()
    return Pagina(totale=totale, pagina=pagina, per_pagina=per_pagina, elementi=[_out(o) for o in righe])


@router.post("", response_model=OpportunitaOut, status_code=201)
def crea(
    dati: OpportunitaNuova,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    if db.get(Cliente, dati.cliente_id) is None or not vede_cliente(db, io, dati.cliente_id):
        raise HTTPException(404, "Cliente non trovato")
    if dati.veicolo_id is not None:
        veicolo = db.get(Veicolo, dati.veicolo_id)
        if veicolo is None or veicolo.cliente_id != dati.cliente_id:
            raise HTTPException(422, "Il veicolo non è di questo cliente")
    if dati.chiamata_id is not None:
        chiamata = db.get(Chiamata, dati.chiamata_id)
        if chiamata is None or chiamata.cliente_id != dati.cliente_id:
            raise HTTPException(422, "La chiamata non è di questo cliente")
    fase = _voce(db, dati.fase_id, ELENCO_FASE, "Fase")
    if fase is None:
        fase = db.scalar(
            select(VoceElenco)
            .where(VoceElenco.elenco == ELENCO_FASE, VoceElenco.effetto == FASE_APERTA, VoceElenco.attivo)
            .order_by(VoceElenco.ordine, VoceElenco.id)
            .limit(1)
        )
        if fase is None:
            raise HTTPException(422, "Manca una fase iniziale nell'elenco delle fasi")
    _voce(db, dati.prodotto_id, ELENCO_PRODOTTO, "Prodotto")
    _controlla_sede(db, dati.sede_id)
    o = Opportunita(
        titolare_id=io.id, fase_id=fase.id,
        **dati.model_dump(exclude={"fase_id", "descrizione"}),
        descrizione=(dati.descrizione or "").strip() or None,
    )
    db.add(o)
    db.flush()
    db.add(OpportunitaFase(opportunita_id=o.id, fase_id=fase.id, utente_id=io.id))
    registra(db, "opportunita_creata", utente=io, oggetto=f"opportunita:{o.id}",
             dettaglio={"cliente_id": o.cliente_id, "fase": fase.nome}, request=request)
    db.commit()
    return _out(_rileggi(db, o.id))


@router.patch("/{opportunita_id}", response_model=OpportunitaOut)
def modifica(
    opportunita_id: int,
    dati: OpportunitaModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    o = db.get(Opportunita, opportunita_id)
    if o is None or (io.ruolo != RUOLO_RESPONSABILE and o.titolare_id != io.id):
        raise HTTPException(404, "Opportunità non trovata")
    modifiche = dati.model_dump(exclude_unset=True)
    fase = _voce(db, modifiche.get("fase_id"), ELENCO_FASE, "Fase") or db.get(VoceElenco, o.fase_id)
    _voce(db, modifiche.get("prodotto_id"), ELENCO_PRODOTTO, "Prodotto")
    _voce(db, modifiche.get("motivo_perdita_id"), ELENCO_MOTIVO_PERDITA, "Motivo di perdita")
    _controlla_sede(db, modifiche.get("sede_id"))
    if "fase_id" in modifiche and modifiche["fase_id"] is None:
        raise HTTPException(422, "Fase non valida")
    if "vendita_aggiuntiva" in modifiche and modifiche["vendita_aggiuntiva"] is None:
        del modifiche["vendita_aggiuntiva"]
    if fase.effetto == FASE_PERSA and not modifiche.get("motivo_perdita_id", o.motivo_perdita_id):
        raise HTTPException(422, "Per chiudere come persa scegli il motivo")
    cambio_fase = fase.id != o.fase_id
    for campo, valore in modifiche.items():
        setattr(o, campo, valore)
    if fase.effetto != FASE_PERSA:
        o.motivo_perdita_id = None
        o.note_perdita = None
    if cambio_fase:
        db.add(OpportunitaFase(opportunita_id=o.id, fase_id=fase.id, utente_id=io.id))
    registra(db, "opportunita_modificata", utente=io, oggetto=f"opportunita:{o.id}",
             dettaglio=dati.model_dump(exclude_unset=True, mode="json"), request=request)
    db.commit()
    return _out(_rileggi(db, o.id))
