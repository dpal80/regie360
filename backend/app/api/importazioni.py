from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit import registra
from app.config import get_settings
from app.db import get_db
from app.models import ImportRiga, Importazione, MappaturaImport, Utente
from app.security import solo_responsabile
from app.services import importa

router = APIRouter(prefix="/importazioni", tags=["import"])


class MappaturaIn(BaseModel):
    mappatura: list[str]


class ConfermaIn(MappaturaIn):
    salva_come: str | None = Field(default=None, max_length=200)


class ImportazioneOut(BaseModel):
    id: int
    nome_file: str
    stato: str
    righe_totali: int
    clienti_nuovi: int
    clienti_aggiornati: int
    veicoli_nuovi: int
    veicoli_aggiornati: int
    passaggi_nuovi: int
    righe_scartate: int
    creato_il: datetime
    completato_il: datetime | None
    creato_da: str | None = None


def _out(imp: Importazione) -> ImportazioneOut:
    campi = {k: getattr(imp, k) for k in ImportazioneOut.model_fields if k != "creato_da"}
    return ImportazioneOut(**campi, creato_da=imp.creato_da.nome if imp.creato_da else None)


def _bozza(db: Session, import_id: int) -> Importazione:
    imp = db.get(Importazione, import_id)
    if imp is None:
        raise HTTPException(404, "Import non trovato")
    if imp.stato != "bozza":
        raise HTTPException(409, "Questo import è già stato chiuso")
    return imp


def _righe(db: Session, imp: Importazione) -> list[tuple[int, list]]:
    return [
        (r.numero, r.dati)
        for r in db.scalars(
            select(ImportRiga).where(ImportRiga.importazione_id == imp.id).order_by(ImportRiga.numero)
        )
    ]


def _verifica_mappatura(imp: Importazione, mappatura: list[str]) -> None:
    errori = importa.controlla_mappatura(imp.intestazioni, mappatura)
    if errori:
        raise HTTPException(422, {"errori": errori})


@router.get("/campi")
def campi(_: Utente = Depends(solo_responsabile)):
    return {
        "campi": [{"chiave": k, "etichetta": v} for k, v in importa.CAMPI.items()],
        "speciali": [
            {"chiave": importa.EXTRA, "etichetta": "Conserva come dato aggiuntivo"},
            {"chiave": importa.IGNORA, "etichetta": "Ignora"},
        ],
    }


@router.get("", response_model=list[ImportazioneOut])
def elenco(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    imps = db.scalars(
        select(Importazione).where(Importazione.stato != "annullato").order_by(Importazione.id.desc()).limit(100)
    ).all()
    return [_out(i) for i in imps]


@router.post("", status_code=201)
async def carica(
    file: UploadFile,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    """Carica il file nella tabella di appoggio e propone l'abbinamento delle colonne."""
    limite = get_settings().import_max_mb * 1024 * 1024
    contenuto = await file.read(limite + 1)
    if len(contenuto) > limite:
        raise HTTPException(413, f"Il file supera i {get_settings().import_max_mb} MB")
    try:
        intestazioni, righe = importa.leggi_file(contenuto)
    except importa.FileNonValido as exc:
        raise HTTPException(422, str(exc)) from None

    # Se una mappatura salvata ha le stesse colonne, si riparte da quella.
    salvata = None
    for m in db.scalars(select(MappaturaImport).order_by(MappaturaImport.aggiornato_il.desc())):
        if set(m.intestazioni) == set(intestazioni):
            salvata = m
            break

    imp = Importazione(
        nome_file=(file.filename or "file")[:300],
        intestazioni=intestazioni,
        righe_totali=len(righe),
        creato_da_id=io.id,
    )
    db.add(imp)
    db.flush()
    db.add_all(
        ImportRiga(importazione_id=imp.id, numero=numero, dati=r) for numero, r in righe
    )
    registra(db, "import_caricato", utente=io, oggetto=f"import:{imp.id}",
             dettaglio={"file": imp.nome_file, "righe": len(righe)}, request=request)
    db.commit()
    return {
        "id": imp.id,
        "nome_file": imp.nome_file,
        "intestazioni": intestazioni,
        "righe_totali": len(righe),
        "mappatura": importa.suggerisci_mappatura(intestazioni, salvata.mappatura if salvata else None),
        "mappatura_salvata": salvata.nome if salvata else None,
        "esempio": [r for _, r in righe[:5]],
    }


@router.post("/{import_id}/anteprima")
def anteprima(
    import_id: int,
    dati: MappaturaIn,
    db: Session = Depends(get_db),
    _: Utente = Depends(solo_responsabile),
):
    imp = _bozza(db, import_id)
    _verifica_mappatura(imp, dati.mappatura)
    return importa.anteprima(imp.intestazioni, _righe(db, imp), dati.mappatura)


@router.post("/{import_id}/conferma", response_model=ImportazioneOut)
def conferma(
    import_id: int,
    dati: ConfermaIn,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    imp = _bozza(db, import_id)
    _verifica_mappatura(imp, dati.mappatura)

    scrittore = importa.Scrittore(db)
    for numero, riga in _righe(db, imp):
        scrittore.scrivi(importa.controlla_riga(numero, riga, imp.intestazioni, dati.mappatura))
    esito = scrittore.chiudi()

    imp.mappatura = dict(zip(imp.intestazioni, dati.mappatura, strict=True))
    imp.stato = "completato"
    imp.completato_il = datetime.now(UTC)
    imp.clienti_nuovi = esito.clienti_nuovi
    imp.clienti_aggiornati = esito.clienti_aggiornati
    imp.veicoli_nuovi = esito.veicoli_nuovi
    imp.veicoli_aggiornati = esito.veicoli_aggiornati
    imp.passaggi_nuovi = esito.passaggi_nuovi
    imp.righe_scartate = esito.righe_scartate
    imp.errori = esito.problemi[:1000]
    db.execute(delete(ImportRiga).where(ImportRiga.importazione_id == imp.id))

    if dati.salva_come and dati.salva_come.strip():
        nome = dati.salva_come.strip()
        m = db.scalar(select(MappaturaImport).where(MappaturaImport.nome == nome))
        if m is None:
            m = MappaturaImport(nome=nome)
            db.add(m)
        m.intestazioni = imp.intestazioni
        m.mappatura = imp.mappatura

    registra(db, "import_confermato", utente=io, oggetto=f"import:{imp.id}", request=request,
             dettaglio={"clienti_nuovi": esito.clienti_nuovi, "veicoli_nuovi": esito.veicoli_nuovi,
                        "righe_scartate": esito.righe_scartate})
    db.commit()
    return _out(imp)


@router.get("/{import_id}")
def dettaglio(import_id: int, db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    imp = db.get(Importazione, import_id)
    if imp is None:
        raise HTTPException(404, "Import non trovato")
    return {**_out(imp).model_dump(), "problemi": imp.errori, "mappatura": imp.mappatura}


@router.delete("/{import_id}", status_code=204)
def annulla(
    import_id: int,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    imp = _bozza(db, import_id)
    imp.stato = "annullato"
    db.execute(delete(ImportRiga).where(ImportRiga.importazione_id == imp.id))
    registra(db, "import_annullato", utente=io, oggetto=f"import:{imp.id}", request=request)
    db.commit()
