from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import registra
from app.db import get_db
from app.models import Team, Utente
from app.security import solo_responsabile

router = APIRouter(prefix="/team", tags=["team"])


class Membro(BaseModel):
    id: int
    nome: str
    ruolo: str
    attivo: bool

    model_config = {"from_attributes": True}


class TeamOut(BaseModel):
    id: int
    nome: str
    attivo: bool
    membri: list[Membro]

    model_config = {"from_attributes": True}


class TeamNuovo(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    membri: list[int] = []


class TeamModifica(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    attivo: bool | None = None
    membri: list[int] | None = None


def _utenti(db: Session, ids: list[int]) -> list[Utente]:
    utenti = db.scalars(select(Utente).where(Utente.id.in_(set(ids)))).all() if ids else []
    if len(utenti) != len(set(ids)):
        raise HTTPException(422, "Uno degli utenti scelti non esiste")
    return list(utenti)


def _nome_libero(db: Session, nome: str, escluso: int | None = None) -> str:
    nome = nome.strip()
    altro = db.scalar(select(Team).where(Team.nome == nome))
    if altro is not None and altro.id != escluso:
        raise HTTPException(409, "Esiste già un team con questo nome")
    return nome


@router.get("", response_model=list[TeamOut])
def elenco(db: Session = Depends(get_db), _: Utente = Depends(solo_responsabile)):
    return db.scalars(select(Team).options(selectinload(Team.membri)).order_by(Team.nome)).all()


@router.post("", response_model=TeamOut, status_code=201)
def crea(
    dati: TeamNuovo,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    team = Team(nome=_nome_libero(db, dati.nome), attivo=True, membri=_utenti(db, dati.membri))
    db.add(team)
    db.flush()
    registra(db, "team_creato", utente=io, oggetto=f"team:{team.id}",
             dettaglio={"nome": team.nome, "membri": dati.membri}, request=request)
    db.commit()
    return team


@router.patch("/{team_id}", response_model=TeamOut)
def modifica(
    team_id: int,
    dati: TeamModifica,
    request: Request,
    db: Session = Depends(get_db),
    io: Utente = Depends(solo_responsabile),
):
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(404, "Team non trovato")
    if dati.nome is not None:
        team.nome = _nome_libero(db, dati.nome, escluso=team.id)
    if dati.attivo is not None:
        team.attivo = dati.attivo
    if dati.membri is not None:
        team.membri = _utenti(db, dati.membri)
    registra(db, "team_modificato", utente=io, oggetto=f"team:{team.id}",
             dettaglio=dati.model_dump(exclude_unset=True), request=request)
    db.commit()
    return team
