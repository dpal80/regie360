from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.audit import registra
from app.db import get_db
from app.models import Audit, Cliente, PassaggioOfficina, Sede, Utente, Veicolo
from app.security import solo_responsabile, utente_corrente

router = APIRouter(tags=["anagrafica"])


class Pagina(BaseModel):
    totale: int
    pagina: int
    per_pagina: int
    elementi: list


class ClienteRiga(BaseModel):
    id: int
    codice: str | None
    nominativo: str
    tipo: str | None
    telefono_cellulare: str | None
    telefono_fisso: str | None
    email: str | None
    num_veicoli: int = 0

    model_config = {"from_attributes": True}


class PassaggioOut(BaseModel):
    id: int
    numero_or: str | None
    sede: str | None
    descrizione: str | None
    data_apertura: date | None
    data_chiusura: date | None


class VeicoloOut(BaseModel):
    id: int
    targa: str | None
    telaio: str | None
    marca: str | None
    modello: str | None
    tipologia: str | None
    data_immatricolazione: date | None
    data_ultimo_passaggio: date | None
    extra: dict
    cliente_id: int | None = None
    cliente_nominativo: str | None = None
    cliente_telefono: str | None = None

    model_config = {"from_attributes": True}


def _veicolo_out(v: Veicolo) -> VeicoloOut:
    out = VeicoloOut.model_validate(v)
    if v.cliente:
        out.cliente_nominativo = v.cliente.nominativo
        out.cliente_telefono = v.cliente.telefono_cellulare or v.cliente.telefono_fisso
    return out


def _cerca_like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


@router.get("/clienti", response_model=Pagina)
def clienti(
    q: str | None = None,
    pagina: int = Query(1, ge=1),
    per_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Utente = Depends(solo_responsabile),
):
    num_veicoli = (
        select(func.count(Veicolo.id)).where(Veicolo.cliente_id == Cliente.id).scalar_subquery()
    )
    query = select(Cliente, num_veicoli.label("n"))
    if q and q.strip():
        like = _cerca_like(q.strip())
        query = query.where(
            or_(
                Cliente.nominativo.ilike(like),
                Cliente.codice.ilike(like),
                Cliente.telefono_cellulare.ilike(like),
                Cliente.telefono_fisso.ilike(like),
                Cliente.email.ilike(like),
                Cliente.id.in_(select(Veicolo.cliente_id).where(
                    or_(Veicolo.targa.ilike(like), Veicolo.telaio.ilike(like)))),
            )
        )
    totale = db.scalar(select(func.count()).select_from(query.subquery()))
    righe = db.execute(
        query.order_by(Cliente.nominativo).offset((pagina - 1) * per_pagina).limit(per_pagina)
    ).all()
    elementi = []
    for c, n in righe:
        r = ClienteRiga.model_validate(c)
        r.num_veicoli = n
        elementi.append(r)
    return Pagina(totale=totale, pagina=pagina, per_pagina=per_pagina, elementi=elementi)


@router.get("/clienti/{cliente_id}")
def cliente(
    cliente_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    c = db.scalar(
        select(Cliente)
        .where(Cliente.id == cliente_id)
        .options(selectinload(Cliente.veicoli).selectinload(Veicolo.passaggi).selectinload(PassaggioOfficina.sede))
    )
    if c is None:
        raise HTTPException(404, "Cliente non trovato")
    registra(db, "cliente_letto", utente=io, oggetto=f"cliente:{c.id}", request=request)
    db.commit()
    return {
        **ClienteRiga.model_validate(c).model_dump(exclude={"num_veicoli"}),
        "escluso_richiami": c.escluso_richiami,
        "consenso_contatto": c.consenso_contatto,
        "extra": c.extra,
        "veicoli": [
            {
                **VeicoloOut.model_validate(v).model_dump(),
                "passaggi": [
                    PassaggioOut(
                        id=p.id,
                        numero_or=p.numero_or,
                        sede=p.sede.nome if p.sede else None,
                        descrizione=p.descrizione,
                        data_apertura=p.data_apertura,
                        data_chiusura=p.data_chiusura,
                    )
                    for p in v.passaggi
                ],
            }
            for v in c.veicoli
        ],
    }


@router.get("/veicoli", response_model=Pagina)
def veicoli(
    q: str | None = None,
    marca: str | None = None,
    sede_id: int | None = None,
    immatricolazione_da: date | None = None,
    immatricolazione_a: date | None = None,
    ultimo_passaggio_da: date | None = None,
    ultimo_passaggio_a: date | None = None,
    pagina: int = Query(1, ge=1),
    per_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: Utente = Depends(solo_responsabile),
):
    query = select(Veicolo).options(selectinload(Veicolo.cliente))
    if q and q.strip():
        like = _cerca_like(q.strip())
        query = query.where(
            or_(
                Veicolo.targa.ilike(like),
                Veicolo.telaio.ilike(like),
                Veicolo.modello.ilike(like),
                Veicolo.cliente_id.in_(select(Cliente.id).where(Cliente.nominativo.ilike(like))),
            )
        )
    if marca:
        query = query.where(Veicolo.marca == marca)
    if sede_id:
        query = query.where(
            Veicolo.id.in_(select(PassaggioOfficina.veicolo_id).where(PassaggioOfficina.sede_id == sede_id))
        )
    if immatricolazione_da:
        query = query.where(Veicolo.data_immatricolazione >= immatricolazione_da)
    if immatricolazione_a:
        query = query.where(Veicolo.data_immatricolazione <= immatricolazione_a)
    if ultimo_passaggio_da:
        query = query.where(Veicolo.data_ultimo_passaggio >= ultimo_passaggio_da)
    if ultimo_passaggio_a:
        query = query.where(Veicolo.data_ultimo_passaggio <= ultimo_passaggio_a)

    totale = db.scalar(select(func.count()).select_from(query.subquery()))
    righe = db.scalars(
        query.order_by(Veicolo.data_immatricolazione.desc().nulls_last(), Veicolo.id)
        .offset((pagina - 1) * per_pagina)
        .limit(per_pagina)
    ).all()
    return Pagina(
        totale=totale, pagina=pagina, per_pagina=per_pagina, elementi=[_veicolo_out(v) for v in righe]
    )


@router.get("/marche")
def marche(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return db.scalars(
        select(Veicolo.marca).where(Veicolo.marca.is_not(None)).distinct().order_by(Veicolo.marca)
    ).all()


@router.get("/sedi")
def sedi(db: Session = Depends(get_db), _: Utente = Depends(utente_corrente)):
    return [{"id": s.id, "nome": s.nome} for s in db.scalars(select(Sede).order_by(Sede.nome))]


@router.get("/riepilogo")
def riepilogo(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return {
        "clienti": db.scalar(select(func.count(Cliente.id))),
        "veicoli": db.scalar(select(func.count(Veicolo.id))),
        "passaggi": db.scalar(select(func.count(PassaggioOfficina.id))),
    }


class AuditOut(BaseModel):
    id: int
    username: str | None
    azione: str
    oggetto: str | None
    dettaglio: dict | None
    ip: str | None
    quando: datetime

    model_config = {"from_attributes": True}


@router.get("/audit", response_model=list[AuditOut])
def audit(
    limite: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _: Utente = Depends(solo_responsabile),
):
    return db.scalars(select(Audit).order_by(Audit.id.desc()).limit(limite)).all()
