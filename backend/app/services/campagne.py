"""Filtri delle campagne e regole di accesso ai contatti."""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.models import (
    CAMPAGNA_ATTIVA,
    CONTATTO_CHIUSO,
    RUOLO_RESPONSABILE,
    Campagna,
    Cliente,
    Contatto,
    PassaggioOfficina,
    TeamMembro,
    Utente,
    Veicolo,
)


class Filtri(BaseModel):
    marca: str | None = None
    sede_id: int | None = None
    immatricolazione_da: date | None = None
    immatricolazione_a: date | None = None
    ultimo_passaggio_da: date | None = None
    ultimo_passaggio_a: date | None = None
    # Parole cercate nella descrizione degli interventi (es. TAGLIANDO, TGA): ne basta una.
    parole: list[str] = Field(default=[], max_length=30)
    solo_con_telefono: bool = True
    # Salta i veicoli che sono già in una campagna attiva e non ancora chiusi.
    escludi_in_campagne_attive: bool = True


def _like(testo: str) -> str:
    return "%" + testo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def veicoli_da_richiamare(f: Filtri) -> Select:
    """Veicoli che rispettano i filtri. Chi si è opposto ai richiami resta sempre fuori."""
    q = select(Veicolo).join(Cliente, Veicolo.cliente_id == Cliente.id).where(Cliente.escluso_richiami.is_(False))
    if f.solo_con_telefono:
        q = q.where(or_(Cliente.telefono_cellulare.is_not(None), Cliente.telefono_fisso.is_not(None)))
    if f.marca:
        q = q.where(Veicolo.marca == f.marca)
    if f.sede_id:
        q = q.where(
            Veicolo.id.in_(select(PassaggioOfficina.veicolo_id).where(PassaggioOfficina.sede_id == f.sede_id))
        )
    if f.immatricolazione_da:
        q = q.where(Veicolo.data_immatricolazione >= f.immatricolazione_da)
    if f.immatricolazione_a:
        q = q.where(Veicolo.data_immatricolazione <= f.immatricolazione_a)
    if f.ultimo_passaggio_da:
        q = q.where(Veicolo.data_ultimo_passaggio >= f.ultimo_passaggio_da)
    if f.ultimo_passaggio_a:
        q = q.where(Veicolo.data_ultimo_passaggio <= f.ultimo_passaggio_a)
    parole = [p.strip() for p in f.parole if p.strip()]
    if parole:
        q = q.where(
            Veicolo.id.in_(
                select(PassaggioOfficina.veicolo_id).where(
                    or_(*[PassaggioOfficina.descrizione.ilike(_like(p)) for p in parole])
                )
            )
        )
    if f.escludi_in_campagne_attive:
        q = q.where(
            ~exists().where(
                Contatto.veicolo_id == Veicolo.id,
                Contatto.stato != CONTATTO_CHIUSO,
                Contatto.campagna_id == Campagna.id,
                Campagna.stato == CAMPAGNA_ATTIVA,
            )
        )
    return q


def team_di(db: Session, utente: Utente) -> list[int]:
    return list(db.scalars(select(TeamMembro.team_id).where(TeamMembro.utente_id == utente.id)))


def vede_campagna(db: Session, utente: Utente, campagna: Campagna) -> bool:
    """Il Responsabile vede tutte le campagne, l'operatore quelle attive dei suoi team."""
    if utente.ruolo == RUOLO_RESPONSABILE:
        return True
    return campagna.stato == CAMPAGNA_ATTIVA and campagna.team_id in team_di(db, utente)


def vede_contatto(utente: Utente, contatto: Contatto) -> bool:
    """L'operatore vede solo i contatti assegnati a lui."""
    return utente.ruolo == RUOLO_RESPONSABILE or contatto.operatore_id == utente.id


def vede_cliente(db: Session, utente: Utente, cliente_id: int) -> bool:
    if utente.ruolo == RUOLO_RESPONSABILE:
        return True
    return bool(
        db.scalar(
            select(Contatto.id).where(Contatto.cliente_id == cliente_id, Contatto.operatore_id == utente.id).limit(1)
        )
    )
