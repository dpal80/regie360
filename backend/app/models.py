from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# JSONB su PostgreSQL, JSON generico altrove.
Json = JSON().with_variant(JSONB(), "postgresql")

# Il super-admin fa tutto quello che fa il Responsabile e in più amministra il sistema:
# password degli utenti locali, altri super-admin, collegamenti ad Active Directory e NethVoice.
RUOLO_SUPERADMIN = "superadmin"
RUOLO_RESPONSABILE = "responsabile"
RUOLO_OPERATORE = "operatore"
# L'amministratore globale è uno solo (l'utente ADMIN_USERNAME): ha i permessi del super-admin,
# il ruolo non si assegna ad altri e il suo utente non può essere modificato da nessuno.
RUOLO_ADMIN_GLOBALE = "admin_globale"
# I ruoli che si possono assegnare dalla pagina Utenti.
RUOLI = (RUOLO_SUPERADMIN, RUOLO_RESPONSABILE, RUOLO_OPERATORE)

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
    # A questo indirizzo arrivano le credenziali provvisorie e i codici per reimpostare la password.
    email: Mapped[str | None] = mapped_column(String(254))
    # Verifica in due passaggi (facoltativa): segreto TOTP cifrato e ultimo codice usato.
    totp_segreto_cifrato: Mapped[str | None] = mapped_column(Text)
    totp_attivo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    totp_ultimo_passo: Mapped[int | None] = mapped_column(Integer)
    # Codice usa e getta per reimpostare la password dimenticata (solo utenti locali).
    reset_codice_hash: Mapped[str | None] = mapped_column(String(255))
    reset_scadenza: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reset_tentativi: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reset_richiesto_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Token di Phone Island e dati SIP dell'utente, cifrati (vedi services/telefonia.py).
    telefono_cifrato: Mapped[str | None] = mapped_column(Text)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)
    tentativi_falliti: Mapped[int] = mapped_column(Integer, default=0)
    bloccato_fino: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_accesso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def admin_globale(self) -> bool:
        return self.ruolo == RUOLO_ADMIN_GLOBALE

    @property
    def superadmin(self) -> bool:
        """Vero anche per l'amministratore globale, che ha tutti i permessi del super-admin."""
        return self.ruolo in (RUOLO_SUPERADMIN, RUOLO_ADMIN_GLOBALE)

    @property
    def responsabile(self) -> bool:
        """Vero anche per il super-admin, che ha tutti i permessi del Responsabile."""
        return self.ruolo in (RUOLO_RESPONSABILE, RUOLO_SUPERADMIN, RUOLO_ADMIN_GLOBALE)


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


class Impostazione(Base):
    """Impostazioni che il Responsabile cambia dalle pagine del CRM (es. Active Directory)."""

    __tablename__ = "impostazione"

    chiave: Mapped[str] = mapped_column(String(50), primary_key=True)
    valore: Mapped[dict] = mapped_column(Json)
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Team(Base):
    __tablename__ = "team"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200), unique=True)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)

    membri: Mapped[list[Utente]] = relationship(secondary="team_membro", order_by=Utente.nome)


class TeamMembro(Base):
    """Un operatore può stare in più team."""

    __tablename__ = "team_membro"

    team_id: Mapped[int] = mapped_column(ForeignKey("team.id", ondelete="CASCADE"), primary_key=True)
    utente_id: Mapped[int] = mapped_column(ForeignKey("utente.id"), primary_key=True, index=True)


ELENCO_ESITO = "esito"
ELENCO_MOTIVO_RICHIAMO = "motivo_richiamo"
ELENCO_FASE = "fase_opportunita"
ELENCO_MOTIVO_PERDITA = "motivo_perdita"
ELENCO_PRODOTTO = "prodotto"
ELENCHI = (ELENCO_ESITO, ELENCO_MOTIVO_RICHIAMO, ELENCO_FASE, ELENCO_MOTIVO_PERDITA, ELENCO_PRODOTTO)

# Cosa succede al contatto dopo una chiamata con quell'esito.
ESITO_RICHIAMO = "richiamo"  # resta in lista, da richiamare
ESITO_CHIUSO = "chiuso"  # esce dalla lista
ESITO_ESCLUSO = "escluso"  # esce dalla lista e il cliente non va più richiamato
EFFETTI_ESITO = (ESITO_RICHIAMO, ESITO_CHIUSO, ESITO_ESCLUSO)

FASE_APERTA = "aperta"
FASE_VINTA = "vinta"
FASE_PERSA = "persa"
EFFETTI_FASE = (FASE_APERTA, FASE_VINTA, FASE_PERSA)


class VoceElenco(Base):
    """Elenchi modificabili dal Responsabile: esiti, motivi di richiamo, fasi, motivi di perdita, prodotti."""

    __tablename__ = "voce_elenco"
    __table_args__ = (UniqueConstraint("elenco", "nome"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    elenco: Mapped[str] = mapped_column(String(30), index=True)
    nome: Mapped[str] = mapped_column(String(200))
    # Esiti: richiamo / chiuso / escluso. Fasi: aperta / vinta / persa. Vuoto negli altri elenchi.
    effetto: Mapped[str | None] = mapped_column(String(20))
    famiglia: Mapped[str | None] = mapped_column(String(200))  # solo prodotti
    ordine: Mapped[int] = mapped_column(Integer, default=0)
    attivo: Mapped[bool] = mapped_column(Boolean, default=True)


CAMPAGNA_ATTIVA = "attiva"
CAMPAGNA_CHIUSA = "chiusa"

CONTATTO_DA_CHIAMARE = "da_chiamare"
CONTATTO_RICHIAMARE = "richiamare"
CONTATTO_CHIUSO = "chiuso"
STATI_CONTATTO = (CONTATTO_DA_CHIAMARE, CONTATTO_RICHIAMARE, CONTATTO_CHIUSO)


class Campagna(Base):
    """Lista di richiamo creata dal Responsabile e assegnata a un team."""

    __tablename__ = "campagna"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    motivo_id: Mapped[int | None] = mapped_column(ForeignKey("voce_elenco.id"))
    filtri: Mapped[dict] = mapped_column(Json, default=dict)
    team_id: Mapped[int] = mapped_column(ForeignKey("team.id"), index=True)
    stato: Mapped[str] = mapped_column(String(20), default=CAMPAGNA_ATTIVA)
    creato_da_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    chiusa_il: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    motivo: Mapped[VoceElenco | None] = relationship()
    team: Mapped[Team] = relationship()


class Contatto(Base):
    """Un veicolo da richiamare dentro una campagna."""

    __tablename__ = "contatto"
    __table_args__ = (UniqueConstraint("campagna_id", "veicolo_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    campagna_id: Mapped[int] = mapped_column(ForeignKey("campagna.id", ondelete="CASCADE"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    veicolo_id: Mapped[int] = mapped_column(ForeignKey("veicolo.id"), index=True)
    # Vuoto finché un operatore del team non lo prende dalla coda.
    operatore_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"), index=True)
    stato: Mapped[str] = mapped_column(String(20), default=CONTATTO_DA_CHIAMARE, index=True)
    priorita: Mapped[int] = mapped_column(Integer, default=0)
    data_richiamo: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    tentativi: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_esito_id: Mapped[int | None] = mapped_column(ForeignKey("voce_elenco.id"))
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    campagna: Mapped[Campagna] = relationship()
    cliente: Mapped[Cliente] = relationship()
    veicolo: Mapped[Veicolo] = relationship()
    operatore: Mapped[Utente | None] = relationship()
    ultimo_esito: Mapped[VoceElenco | None] = relationship()


class Chiamata(Base):
    __tablename__ = "chiamata"

    id: Mapped[int] = mapped_column(primary_key=True)
    contatto_id: Mapped[int | None] = mapped_column(ForeignKey("contatto.id", ondelete="SET NULL"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    operatore_id: Mapped[int] = mapped_column(ForeignKey("utente.id"), index=True)
    direzione: Mapped[str] = mapped_column(String(10), default="uscita")
    numero: Mapped[str | None] = mapped_column(String(30))
    inizio: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    durata_secondi: Mapped[int | None] = mapped_column(Integer)
    esito_id: Mapped[int | None] = mapped_column(ForeignKey("voce_elenco.id"))
    # ID della chiamata su NethVoice: lo compilerà la telefonia (fase 3).
    unique_id: Mapped[str | None] = mapped_column(String(100))

    operatore: Mapped[Utente] = relationship()
    esito: Mapped[VoceElenco | None] = relationship()


class Nota(Base):
    __tablename__ = "nota"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    chiamata_id: Mapped[int | None] = mapped_column(ForeignKey("chiamata.id", ondelete="SET NULL"))
    autore_id: Mapped[int] = mapped_column(ForeignKey("utente.id"))
    testo: Mapped[str] = mapped_column(Text)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    autore: Mapped[Utente] = relationship()


class Opportunita(Base):
    """Appuntamento o vendita nata da una chiamata (o creata a mano)."""

    __tablename__ = "opportunita"

    id: Mapped[int] = mapped_column(primary_key=True)
    titolare_id: Mapped[int] = mapped_column(ForeignKey("utente.id"), index=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("cliente.id"), index=True)
    veicolo_id: Mapped[int | None] = mapped_column(ForeignKey("veicolo.id"))
    chiamata_id: Mapped[int | None] = mapped_column(ForeignKey("chiamata.id", ondelete="SET NULL"))
    fase_id: Mapped[int] = mapped_column(ForeignKey("voce_elenco.id"), index=True)
    data_appuntamento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    sede_id: Mapped[int | None] = mapped_column(ForeignKey("sede.id"))
    descrizione: Mapped[str | None] = mapped_column(Text)
    ammontare: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    vendita_aggiuntiva: Mapped[bool] = mapped_column(Boolean, default=False)
    prezzo_vendita: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    prodotto_id: Mapped[int | None] = mapped_column(ForeignKey("voce_elenco.id"))
    motivo_perdita_id: Mapped[int | None] = mapped_column(ForeignKey("voce_elenco.id"))
    note_perdita: Mapped[str | None] = mapped_column(Text)
    creato_il: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    aggiornato_il: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    titolare: Mapped[Utente] = relationship()
    cliente: Mapped[Cliente] = relationship()
    veicolo: Mapped[Veicolo | None] = relationship()
    sede: Mapped[Sede | None] = relationship()
    fase: Mapped[VoceElenco] = relationship(foreign_keys=[fase_id])
    prodotto: Mapped[VoceElenco | None] = relationship(foreign_keys=[prodotto_id])
    motivo_perdita: Mapped[VoceElenco | None] = relationship(foreign_keys=[motivo_perdita_id])


class OpportunitaFase(Base):
    """Storico dei cambi di fase: serve a misurare il tempo dall'appuntamento alla chiusura."""

    __tablename__ = "opportunita_fase"

    id: Mapped[int] = mapped_column(primary_key=True)
    opportunita_id: Mapped[int] = mapped_column(ForeignKey("opportunita.id", ondelete="CASCADE"), index=True)
    fase_id: Mapped[int] = mapped_column(ForeignKey("voce_elenco.id"))
    utente_id: Mapped[int | None] = mapped_column(ForeignKey("utente.id"))
    quando: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
