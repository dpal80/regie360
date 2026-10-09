from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# JSONB su PostgreSQL, JSON generico altrove.
Json = JSON().with_variant(JSONB(), "postgresql")

RUOLO_RESPONSABILE = "responsabile"
RUOLO_OPERATORE = "operatore"
RUOLI = (RUOLO_RESPONSABILE, RUOLO_OPERATORE)

ORIGINE_AD = "ad"
ORIGINE_LOCALE = "locale"


class Utente(Base):
    __tablename__ = "utente"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True)
    nome: Mapped[str] = mapped_column(String(200))
    ruolo: Mapped[str] = mapped_column(String(20))
    origine: Mapped[str] = mapped_column(String(10), default=ORIGINE_AD)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    # Utenti locali: al primo accesso (o dopo un reset) devono scegliere una nuova password.
    deve_cambiare_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    interno: Mapped[str | None] = mapped_column(String(20))
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    tentativi_falliti: Mapped[int] = mapped_column(Integer, default=0)
    bloccato_fino: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_accesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Sede(Base):
    __tablename__ = "sede"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True)


class Cliente(Base):
    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(primary_key=True)
    codice: Mapped[str | None] = mapped_column(String(50), unique=True)
    nominativo: Mapped[str] = mapped_column(String(300), index=True)
    tipo: Mapped[str | None] = mapped_column(String(10))  # privato / azienda
    telefono_cellulare: Mapped[str | None] = mapped_column(String(30), index=True)
    telefono_fisso: Mapped[str | None] = mapped_column(String(30), index=True)
    email: Mapped[str | None] = mapped_column(String(254))
    escluso_richiami: Mapped[bool] = mapped_column(Boolean, default=False)
    consenso_contatto: Mapped[bool | None] = mapped_column(Boolean)
    extra: Mapped[dict] = mapped_column(Json, default=dict)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    veicoli: Mapped[list["Veicolo"]] = relationship(back_populates="cliente")


class Veicolo(Base):
    __tablename__ = "veicolo"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("cliente.id"), index=True)
    targa: Mapped[str | None] = mapped_column(String(20), index=True)
    telaio: Mapped[str | None] = mapped_column(String(30), unique=True)
    marca: Mapped[str | None] = mapped_column(String(100), index=True)
    modello: Mapped[str | None] = mapped_column(String(200))
    tipologia: Mapped[str | None] = mapped_column(String(100))
    data_immatricolazione: Mapped[date | None] = mapped_column(Date, index=True)
    data_ultimo_passaggio: Mapped[date | None] = mapped_column(Date, index=True)
    extra: Mapped[dict] = mapped_column(Json, default=dict)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    cliente: Mapped[Cliente | None] = relationship(back_populates="veicoli")
    passaggi: Mapped[list["PassaggioOfficina"]] = relationship(
        back_populates="veicolo", order_by="PassaggioOfficina.data_apertura.desc()"
    )


class PassaggioOfficina(Base):
    __tablename__ = "passaggio_officina"

    id: Mapped[int] = mapped_column(primary_key=True)
    veicolo_id: Mapped[int] = mapped_column(ForeignKey("veicolo.id"), index=True)
    numero_or: Mapped[str | None] = mapped_column(String(50), unique=True)
    sede_id: Mapped[int | None] = mapped_column(ForeignKey("sede.id"))
    descrizione: Mapped[str | None] = mapped_column(Text)
    data_apertura: Mapped[date | None] = mapped_column(Date)
    data_chiusura: Mapped[date | None] = mapped_column(Date)

    veicolo: Mapped[Veicolo] = relationship(back_populates="passaggi")
    sede: Mapped[Sede | None] = relationship()


class MappaturaImport(Base):
    """Abbinamento colonne del file -> campi del CRM, salvato per riusarlo."""

    __tablename__ = "mappatura_import"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True)
    intestazioni: Mapped[list] = mapped_column(Json)
    mappatura: Mapped[dict] = mapped_column(Json)
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Importazione(Base):
    __tablename__ = "importazione"

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(20), default="xls")
    nome_file: Mapped[str] = mapped_column(String(300))
    stato: Mapped[str] = mapped_column(String(20), default="bozza")  # bozza, completato, annullato
    intestazioni: Mapped[list] = mapped_column(Json, default=list)
    mappatura: Mapped[dict | None] = mapped_column(Json)
    righe_totali: Mapped[int] = mapped_column(Integer, default=0)
    clienti_nuovi: Mapped[int] = mapped_column(Integer, default=0)
    clienti_aggiornati: Mapped[int] = mapped_column(Integer, default=0)
    veicoli_nuovi: Mapped[int] = mapped_column(Integer, default=0)
    veicoli_aggiornati: Mapped[int] = mapped_column(Integer, default=0)
    passaggi_nuovi: Mapped[int] = mapped_column(Integer, default=0)
    righe_scartate: Mapped[int] = mapped_column(Integer, default=0)
    errori: Mapped[list] = mapped_column(Json, default=list)
    creato_da_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completato_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    creato_da: Mapped[Utente | None] = relationship()


class ImportRiga(Base):
    """Tabella di appoggio: le righe del file restano qui finché l'import non è confermato."""

    __tablename__ = "import_riga"

    id: Mapped[int] = mapped_column(primary_key=True)
    importazione_id: Mapped[int] = mapped_column(
        ForeignKey("importazione.id", ondelete="CASCADE"), index=True
    )
    numero: Mapped[int] = mapped_column(Integer)  # numero di riga nel file
    dati: Mapped[list] = mapped_column(Json)


class Audit(Base):
    __tablename__ = "audit"

    id: Mapped[int] = mapped_column(primary_key=True)
    utente_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    username: Mapped[str | None] = mapped_column(String(150))
    azione: Mapped[str] = mapped_column(String(50), index=True)
    oggetto: Mapped[str | None] = mapped_column(String(200))
    dettaglio: Mapped[dict | None] = mapped_column(Json)
    ip: Mapped[str | None] = mapped_column(String(64))
    quando: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
