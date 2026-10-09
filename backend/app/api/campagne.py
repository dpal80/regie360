from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, insert, literal, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.audit import registra
from app.db import get_db
from app.models import (
    CAMPAGNA_ATTIVA,
    CAMPAGNA_CHIUSA,
    CONTATTO_CHIUSO,
    CONTATTO_DA_CHIAMARE,
    CONTATTO_RICHIAMARE,
    ELENCO_ESITO,
    ELENCO_MOTIVO_RICHIAMO,
    ESITO_ESCLUSO,
    ESITO_RICHIAMO,
    RUOLO_RESPONSABILE,
    STATI_CONTATTO,
    Campagna,
    Chiamata,
    Cliente,
    Contatto,
    Nota,
    Opportunita,
    PassaggioOfficina,
    Team,
    TeamMembro,
    Utente,
    Veicolo,
    VoceElenco,
)
from app.security import solo_responsabile, utente_corrente
from app.services.campagne import (
    Filtri,
    team_di,
    vede_campagna,
    vede_cliente,
    vede_contatto,
    veicoli_da_richiamare,
)

router = APIRouter(tags=["campagne"])


class Anteprima(BaseModel):
    veicoli: int
    clienti: int
    esempi: list[dict]


class CampagnaNuova(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    motivo_id: int | None = None
    team_id: int
    filtri: Filtri = Filtri()


class CampagnaModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    team_id: int | None = None
    stato: str | None = None


class CampagnaOut(BaseModel):
    id: int
    nome: str
    motivo: str | None
    team_id: int
    team: str
    stato: str
    filtri: dict
    creato_il: datetime
    totale: int = 0
    da_chiamare: int = 0
    richiamare: int = 0
    chiusi: int = 0
    # Solo per chi chiama: quanti contatti sono ancora liberi nella coda del team e quanti sono suoi.
    in_coda: int = 0
    miei: int = 0


class ContattoRiga(BaseModel):
    id: int
    campagna_id: int
    campagna: str
    cliente_id: int
    cliente: str
    telefono: str | None
    veicolo: str
    targa: str | None
    operatore_id: int | None
    operatore: str | None
    stato: str
    data_richiamo: datetime | None
    tentativi: int
    ultimo_esito: str | None


class Pagina(BaseModel):
    totale: int
    pagina: int
    per_pagina: int
    elementi: list[ContattoRiga]


class ChiamataNuova(BaseModel):
    esito_id: int
    nota: str | None = Field(default=None, max_length=5000)
    data_richiamo: datetime | None = None
    numero: str | None = Field(default=None, max_length=30)
    durata_secondi: int | None = Field(default=None, ge=0, le=86400)


class NotaNuova(BaseModel):
    testo: str = Field(min_length=1, max_length=5000)


class ContattoModifica(BaseModel):
    operatore_id: int | None = None
    priorita: int | None = Field(default=None, ge=0, le=9)


def _team_attivo(db: Session, team_id: int) -> Team:
    team = db.get(Team, team_id)
    if team is None or not team.attivo:
        raise HTTPException(422, "Scegli un team attivo")
    return team


def _campagna(db: Session, campagna_id: int, utente: Utente) -> Campagna:
    campagna = db.get(Campagna, campagna_id)
    if campagna is None or not vede_campagna(db, utente, campagna):
        raise HTTPException(404, "Campagna non trovata")
    return campagna


def _contatto(db: Session, contatto_id: int, utente: Utente) -> Contatto:
    contatto = db.get(Contatto, contatto_id)
    if contatto is None or not vede_contatto(utente, contatto):
        raise HTTPException(404, "Contatto non trovato")
    return contatto


def _conteggi(db: Session, campagne: list[Campagna], utente: Utente) -> list[CampagnaOut]:
    ids = [c.id for c in campagne]
    per_stato: dict[int, dict[str, int]] = {}
    in_coda: dict[int, int] = {}
    miei: dict[int, int] = {}
    if ids:
        for cid, stato, n in db.execute(
            select(Contatto.campagna_id, Contatto.stato, func.count())
            .where(Contatto.campagna_id.in_(ids))
            .group_by(Contatto.campagna_id, Contatto.stato)
        ):
            per_stato.setdefault(cid, {})[stato] = n
        aperti = Contatto.stato != CONTATTO_CHIUSO
        in_coda = dict(db.execute(
            select(Contatto.campagna_id, func.count())
            .where(Contatto.campagna_id.in_(ids), aperti, Contatto.operatore_id.is_(None))
            .group_by(Contatto.campagna_id)
        ).all())
        miei = dict(db.execute(
            select(Contatto.campagna_id, func.count())
            .where(Contatto.campagna_id.in_(ids), aperti, Contatto.operatore_id == utente.id)
            .group_by(Contatto.campagna_id)
        ).all())
    out = []
    for c in campagne:
        s = per_stato.get(c.id, {})
        out.append(CampagnaOut(
            id=c.id, nome=c.nome, motivo=c.motivo.nome if c.motivo else None, team_id=c.team_id,
            team=c.team.nome, stato=c.stato, filtri=c.filtri, creato_il=c.creato_il,
            totale=sum(s.values()), da_chiamare=s.get(CONTATTO_DA_CHIAMARE, 0),
            richiamare=s.get(CONTATTO_RICHIAMARE, 0), chiusi=s.get(CONTATTO_CHIUSO, 0),
            in_coda=in_coda.get(c.id, 0), miei=miei.get(c.id, 0),
        ))
    return out


def _riga(c: Contatto) -> ContattoRiga:
    return ContattoRiga(
        id=c.id, campagna_id=c.campagna_id, campagna=c.campagna.nome, cliente_id=c.cliente_id,
        cliente=c.cliente.nominativo, telefono=c.cliente.telefono_cellulare or c.cliente.telefono_fisso,
        veicolo=" ".join(x for x in (c.veicolo.marca, c.veicolo.modello) if x), targa=c.veicolo.targa,
        operatore_id=c.operatore_id, operatore=c.operatore.nome if c.operatore else None, stato=c.stato, data_richiamo=c.data_richiamo,
        tentativi=c.tentativi, ultimo_esito=c.ultimo_esito.nome if c.ultimo_esito else None,
    )


_CARICA_RIGA = (
    selectinload(Contatto.campagna), selectinload(Contatto.cliente), selectinload(Contatto.veicolo),
    selectinload(Contatto.operatore), selectinload(Contatto.ultimo_esito),
)


@router.post("/campagne/anteprima", response_model=Anteprima)
def anteprima(filtri: Filtri, db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    """Quanti veicoli finirebbero nella campagna con questi filtri, prima di crearla."""
    trovati = veicoli_da_richiamare(filtri).subquery()
    veicoli = db.scalar(select(func.count()).select_from(trovati))
    clienti = db.scalar(select(func.count(func.distinct(trovati.c.cliente_id))))
    esempi = db.scalars(
        veicoli_da_richiamare(filtri).options(selectinload(Veicolo.cliente)).order_by(Veicolo.id).limit(10)
    ).all()
    return Anteprima(veicoli=veicoli, clienti=clienti, esempi=[
        {"targa": v.targa, "veicolo": " ".join(x for x in (v.marca, v.modello) if x),
         "cliente": v.cliente.nominativo, "data_immatricolazione": v.data_immatricolazione,
         "data_ultimo_passaggio": v.data_ultimo_passaggio}
        for v in esempi
    ])


@router.post("/campagne", response_model=CampagnaOut, status_code=201)
def crea(
    dati: CampagnaNuova,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    _team_attivo(db, dati.team_id)
    if dati.motivo_id is not None:
        motivo = db.get(VoceElenco, dati.motivo_id)
        if motivo is None or motivo.elenco != ELENCO_MOTIVO_RICHIAMO:
            raise HTTPException(422, "Motivo di richiamo non valido")
    campagna = Campagna(
        nome=dati.nome.strip(), motivo_id=dati.motivo_id, team_id=dati.team_id,
        filtri=dati.filtri.model_dump(mode="json"), stato=CAMPAGNA_ATTIVA, creato_da_id=io.id,
    )
    db.add(campagna)
    db.flush()
    trovati = veicoli_da_richiamare(dati.filtri).subquery()
    db.execute(
        insert(Contatto).from_select(
            ["campagna_id", "cliente_id", "veicolo_id", "stato", "priorita", "tentativi"],
            select(literal(campagna.id), trovati.c.cliente_id, trovati.c.id,
                   literal(CONTATTO_DA_CHIAMARE), literal(0), literal(0)),
        )
    )
    creati = db.scalar(select(func.count(Contatto.id)).where(Contatto.campagna_id == campagna.id))
    if not creati:
        db.rollback()
        raise HTTPException(422, "Nessun veicolo con questi filtri: la campagna sarebbe vuota")
    registra(db, "campagna_creata", utente=io, oggetto=f"campagna:{campagna.id}",
             dettaglio={"nome": campagna.nome, "contatti": creati, "team_id": campagna.team_id}, request=request)
    db.commit()
    return _conteggi(db, [campagna], io)[0]


@router.get("/campagne", response_model=list[CampagnaOut])
def elenco(db: Session = Depends(get_db), io: Utente = Depends(utente_corrente)):
    query = select(Campagna).options(selectinload(Campagna.team), selectinload(Campagna.motivo))
    if io.ruolo != RUOLO_RESPONSABILE:
        query = query.where(Campagna.stato == CAMPAGNA_ATTIVA, Campagna.team_id.in_(team_di(db, io)))
    return _conteggi(db, list(db.scalars(query.order_by(Campagna.id.desc()))), io)


@router.get("/campagne/{campagna_id}")
def dettaglio(campagna_id: int, db: Session = Depends(get_db), io: Utente = Depends(solo_responsabile)):
    campagna = _campagna(db, campagna_id, io)
    per_operatore = db.execute(
        select(Utente.nome, Contatto.stato, func.count())
        .join(Utente, Contatto.operatore_id == Utente.id)
        .where(Contatto.campagna_id == campagna.id)
        .group_by(Utente.nome, Contatto.stato)
        .order_by(Utente.nome)
    ).all()
    operatori: dict[str, dict[str, int]] = {}
    for nome, stato, n in per_operatore:
        operatori.setdefault(nome, {s: 0 for s in STATI_CONTATTO})[stato] = n
    membri = db.execute(
        select(Utente.id, Utente.nome)
        .join(TeamMembro, TeamMembro.utente_id == Utente.id)
        .where(TeamMembro.team_id == campagna.team_id, Utente.attivo)
        .order_by(Utente.nome)
    ).all()
    return {
        **_conteggi(db, [campagna], io)[0].model_dump(),
        "operatori": [{"nome": nome, **stati} for nome, stati in operatori.items()],
        "membri": [{"id": i, "nome": n} for i, n in membri],
    }


@router.patch("/campagne/{campagna_id}", response_model=CampagnaOut)
def modifica(
    campagna_id: int,
    dati: CampagnaModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    campagna = _campagna(db, campagna_id, io)
    if dati.nome is not None:
        campagna.nome = dati.nome.strip()
    if dati.team_id is not None and dati.team_id != campagna.team_id:
        _team_attivo(db, dati.team_id)
        campagna.team_id = dati.team_id
        # I contatti ancora aperti tornano nella coda, a disposizione del nuovo team.
        db.execute(
            update(Contatto)
            .where(Contatto.campagna_id == campagna.id, Contatto.stato != CONTATTO_CHIUSO)
            .values(operatore_id=None)
        )
    if dati.stato is not None:
        if dati.stato not in (CAMPAGNA_ATTIVA, CAMPAGNA_CHIUSA):
            raise HTTPException(422, "Stato non valido")
        campagna.stato = dati.stato
        campagna.chiusa_il = datetime.now(UTC) if dati.stato == CAMPAGNA_CHIUSA else None
    registra(db, "campagna_modificata", utente=io, oggetto=f"campagna:{campagna.id}",
             dettaglio=dati.model_dump(exclude_unset=True), request=request)
    db.commit()
    db.refresh(campagna)
    return _conteggi(db, [campagna], io)[0]


@router.get("/campagne/{campagna_id}/contatti", response_model=Pagina)
def contatti_campagna(
    campagna_id: int,
    stato: str | None = None,
    pagina: int = Query(1, ge=1),
    per_pagina: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    _campagna(db, campagna_id, io)
    query = select(Contatto).where(Contatto.campagna_id == campagna_id)
    if stato:
        query = query.where(Contatto.stato == stato)
    totale = db.scalar(select(func.count()).select_from(query.subquery()))
    righe = db.scalars(
        query.options(*_CARICA_RIGA).order_by(Contatto.id).offset((pagina - 1) * per_pagina).limit(per_pagina)
    ).all()
    return Pagina(totale=totale, pagina=pagina, per_pagina=per_pagina, elementi=[_riga(c) for c in righe])


@router.post("/campagne/{campagna_id}/prossimo")
def prossimo(
    campagna_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    """Dà a chi chiama il prossimo contatto: prima i suoi richiami scaduti, poi uno libero dalla coda del team."""
    campagna = _campagna(db, campagna_id, io)
    if campagna.stato != CAMPAGNA_ATTIVA:
        raise HTTPException(400, "La campagna è chiusa")
    adesso = datetime.now(UTC)
    mio = db.scalar(
        select(Contatto)
        .where(
            Contatto.campagna_id == campagna.id,
            Contatto.operatore_id == io.id,
            or_(
                Contatto.stato == CONTATTO_DA_CHIAMARE,
                (Contatto.stato == CONTATTO_RICHIAMARE)
                & or_(Contatto.data_richiamo.is_(None), Contatto.data_richiamo <= adesso),
            ),
        )
        .order_by(Contatto.data_richiamo.nulls_last(), Contatto.id)
        .limit(1)
    )
    if mio is not None:
        return {"contatto_id": mio.id}
    # SKIP LOCKED: due operatori che premono insieme ricevono due contatti diversi.
    libero = db.scalar(
        select(Contatto)
        .where(
            Contatto.campagna_id == campagna.id,
            Contatto.operatore_id.is_(None),
            Contatto.stato != CONTATTO_CHIUSO,
        )
        .order_by(Contatto.priorita.desc(), Contatto.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if libero is None:
        raise HTTPException(404, "Non ci sono altri contatti da chiamare adesso in questa campagna")
    libero.operatore_id = io.id
    registra(db, "contatto_preso", utente=io, oggetto=f"contatto:{libero.id}", request=request)
    db.commit()
    return {"contatto_id": libero.id}


@router.get("/contatti/miei", response_model=list[ContattoRiga])
def miei(
    stato: str | None = None,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    """I contatti ancora aperti assegnati a chi è collegato, con i richiami più vicini in cima."""
    query = (
        select(Contatto)
        .join(Campagna, Contatto.campagna_id == Campagna.id)
        .where(Contatto.operatore_id == io.id, Campagna.stato == CAMPAGNA_ATTIVA)
    )
    query = query.where(Contatto.stato == stato) if stato else query.where(Contatto.stato != CONTATTO_CHIUSO)
    righe = db.scalars(
        query.options(*_CARICA_RIGA).order_by(Contatto.data_richiamo.nulls_last(), Contatto.id).limit(500)
    ).all()
    return [_riga(c) for c in righe]


@router.get("/contatti/{contatto_id}")
def contatto(
    contatto_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    c = _contatto(db, contatto_id, io)
    cliente = c.cliente
    passaggi = db.scalars(
        select(PassaggioOfficina)
        .where(PassaggioOfficina.veicolo_id == c.veicolo_id)
        .options(selectinload(PassaggioOfficina.sede))
        .order_by(PassaggioOfficina.data_apertura.desc().nulls_last())
        .limit(20)
    ).all()
    chiamate = db.scalars(
        select(Chiamata)
        .where(Chiamata.cliente_id == cliente.id)
        .options(selectinload(Chiamata.operatore), selectinload(Chiamata.esito))
        .order_by(Chiamata.inizio.desc())
        .limit(50)
    ).all()
    note = db.scalars(
        select(Nota).where(Nota.cliente_id == cliente.id).options(selectinload(Nota.autore))
        .order_by(Nota.creato_il.desc()).limit(50)
    ).all()
    opportunita = db.scalars(
        select(Opportunita).where(Opportunita.cliente_id == cliente.id)
        .options(selectinload(Opportunita.fase), selectinload(Opportunita.titolare))
        .order_by(Opportunita.id.desc()).limit(20)
    ).all()
    registra(db, "contatto_letto", utente=io, oggetto=f"contatto:{c.id}", request=request)
    db.commit()
    v = c.veicolo
    return {
        **_riga(c).model_dump(),
        "campagna_stato": c.campagna.stato,
        "motivo": c.campagna.motivo.nome if c.campagna.motivo else None,
        "cliente_dati": {
            "id": cliente.id, "nominativo": cliente.nominativo, "codice": cliente.codice,
            "telefono_cellulare": cliente.telefono_cellulare, "telefono_fisso": cliente.telefono_fisso,
            "email": cliente.email,
        },
        "veicolo_dati": {
            "id": v.id, "targa": v.targa, "marca": v.marca, "modello": v.modello,
            "data_immatricolazione": v.data_immatricolazione, "data_ultimo_passaggio": v.data_ultimo_passaggio,
        },
        "passaggi": [
            {"id": p.id, "numero_or": p.numero_or, "sede": p.sede.nome if p.sede else None,
             "descrizione": p.descrizione, "data_apertura": p.data_apertura}
            for p in passaggi
        ],
        "chiamate": [
            {"id": x.id, "inizio": x.inizio, "operatore": x.operatore.nome,
             "esito": x.esito.nome if x.esito else None, "contatto_id": x.contatto_id}
            for x in chiamate
        ],
        "note": [{"id": n.id, "testo": n.testo, "autore": n.autore.nome, "creato_il": n.creato_il} for n in note],
        "opportunita": [
            {"id": o.id, "fase": o.fase.nome, "titolare": o.titolare.nome,
             "data_appuntamento": o.data_appuntamento, "descrizione": o.descrizione}
            for o in opportunita
        ],
    }


@router.patch("/contatti/{contatto_id}", response_model=ContattoRiga)
def modifica_contatto(
    contatto_id: int,
    dati: ContattoModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Il Responsabile può assegnare un contatto a un operatore del team, o rimetterlo in coda."""
    c = _contatto(db, contatto_id, io)
    modifiche = dati.model_dump(exclude_unset=True)
    if "operatore_id" in modifiche:
        if dati.operatore_id is not None and not db.scalar(
            select(TeamMembro.utente_id).where(
                TeamMembro.team_id == c.campagna.team_id, TeamMembro.utente_id == dati.operatore_id
            )
        ):
            raise HTTPException(422, "L'operatore non fa parte del team della campagna")
        c.operatore_id = dati.operatore_id
    if dati.priorita is not None:
        c.priorita = dati.priorita
    registra(db, "contatto_modificato", utente=io, oggetto=f"contatto:{c.id}", dettaglio=modifiche, request=request)
    db.commit()
    db.refresh(c)
    return _riga(c)


@router.post("/contatti/{contatto_id}/chiamate", status_code=201)
def registra_chiamata(
    contatto_id: int,
    dati: ChiamataNuova,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    """Registra la telefonata e sposta il contatto secondo l'esito scelto."""
    c = _contatto(db, contatto_id, io)
    if c.campagna.stato != CAMPAGNA_ATTIVA:
        raise HTTPException(400, "La campagna è chiusa")
    esito = db.get(VoceElenco, dati.esito_id)
    if esito is None or esito.elenco != ELENCO_ESITO or not esito.attivo:
        raise HTTPException(422, "Esito non valido")
    cliente = c.cliente
    chiamata = Chiamata(
        contatto_id=c.id, cliente_id=cliente.id, operatore_id=io.id, direzione="uscita",
        numero=(dati.numero or cliente.telefono_cellulare or cliente.telefono_fisso),
        durata_secondi=dati.durata_secondi, esito_id=esito.id,
    )
    db.add(chiamata)
    db.flush()
    if dati.nota and dati.nota.strip():
        db.add(Nota(cliente_id=cliente.id, chiamata_id=chiamata.id, autore_id=io.id, testo=dati.nota.strip()))

    c.tentativi += 1
    c.ultimo_esito_id = esito.id
    if c.operatore_id is None:
        c.operatore_id = io.id
    if esito.effetto == ESITO_RICHIAMO:
        c.stato = CONTATTO_RICHIAMARE
        c.data_richiamo = dati.data_richiamo
    else:
        c.stato = CONTATTO_CHIUSO
        c.data_richiamo = None
    if esito.effetto == ESITO_ESCLUSO:
        # Chi si oppone ai richiami esce da tutte le liste, non solo da questa.
        cliente.escluso_richiami = True
        db.execute(
            update(Contatto)
            .where(Contatto.cliente_id == cliente.id, Contatto.stato != CONTATTO_CHIUSO, Contatto.id != c.id)
            .values(stato=CONTATTO_CHIUSO, data_richiamo=None)
        )
    registra(db, "chiamata_registrata", utente=io, oggetto=f"contatto:{c.id}",
             dettaglio={"chiamata_id": chiamata.id, "esito": esito.nome}, request=request)
    db.commit()
    return {"chiamata_id": chiamata.id, "stato": c.stato}


@router.post("/clienti/{cliente_id}/note", status_code=201)
def aggiungi_nota(
    cliente_id: int,
    dati: NotaNuova,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(utente_corrente),
):
    if db.get(Cliente, cliente_id) is None or not vede_cliente(db, io, cliente_id):
        raise HTTPException(404, "Cliente non trovato")
    nota = Nota(cliente_id=cliente_id, autore_id=io.id, testo=dati.testo.strip())
    db.add(nota)
    db.flush()
    registra(db, "nota_creata", utente=io, oggetto=f"cliente:{cliente_id}", request=request)
    db.commit()
    return {"id": nota.id}
