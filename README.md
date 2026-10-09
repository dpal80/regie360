# Regie360

<img src="docs/logo/logo.svg" alt="Regie360" width="360">

Regie360 è il CRM web per le chiamate di ricontatto dei clienti dell'officina e concessionaria REGIE AUTO.
Gira tutto in locale con Docker Compose: nessun servizio cloud esterno.

Il CRM copre le prime due fasi del documento di architettura:

- **fase 1 (base)**: login, utenti e ruoli, import del file Excel con abbinamento delle colonne,
  anagrafica clienti e veicoli, registro attività;
- **fase 2 (chiamate)**: team, campagne con filtri, coda delle chiamate, esiti, note e opportunità.

La telefonia (Phone Island) arriva con la fase 3: per ora l'operatore chiama dal suo telefono e
registra a mano l'esito.

## Cosa c'è dentro

| Container | Cosa fa |
|-----------|---------|
| `proxy`   | Nginx: HTTPS, serve il frontend React e inoltra `/api` al backend |
| `backend` | FastAPI (Python): login, permessi, import, API |
| `db`      | PostgreSQL 16 |

Il worker per l'import in background e la sincronizzazione con Infinity arriveranno con la fase 5:
per ora l'import gira dentro il backend, che regge senza problemi file da decine di migliaia di righe.

## Avvio

```sh
cp .env.example .env      # poi compila almeno POSTGRES_PASSWORD, JWT_SECRET, ADMIN_PASSWORD
docker compose up -d --build
```

Apri `https://<server>/` (o `https://localhost:<HTTPS_PORT>/`) ed entra con l'utente `admin` e la
`ADMIN_PASSWORD` del file `.env`.

Al primo avvio il proxy crea un certificato autofirmato in `certs/`. In sede va sostituito con
uno rilasciato dalla CA interna: si mettono `certs/crm.crt` e `certs/crm.key` e si riavvia il proxy.

### Utenti di esempio per le prove

Su un'installazione di prova si possono creare un Responsabile e tre Operatori locali:

```sh
docker compose exec backend python -m app.semina
```

Nomi utente e password sono in `backend/app/semina.py`. Sono pubblici, quindi il comando non va
mai lanciato sul server in sede (con l'Active Directory configurato si rifiuta di partire).

### Portare il CRM sul server in sede (senza internet)

```sh
docker compose build
docker save crm-regie-auto-backend crm-regie-auto-proxy postgres:16-alpine | gzip > crm-immagini.tar.gz
# sul server: docker load < crm-immagini.tar.gz, poi copia docker-compose.yml e .env e lancia docker compose up -d
```

## Login

- **Utenti di dominio**: entrano con nome utente e password di Windows. Il backend verifica la password
  sull'Active Directory via LDAPS. Il collegamento si imposta dalla pagina **Active Directory**
  (server, dominio, porta, certificato della CA interna), dove si può anche provare con un utente di
  dominio prima di salvare. Le variabili `AD_SERVER`, `AD_DOMAIN` e `AD_CA_FILE` del file `.env` restano
  valide finché dalla pagina non si salva nulla.
  L'AD controlla solo la password: chi può entrare e con quale ruolo lo decide il Responsabile nella
  pagina **Utenti**. Un utente AD non aggiunto al CRM non entra.
- **Utenti locali**: il Responsabile può creare anche utenti con una password del CRM (per chi non ha un
  account di dominio). Riceve una password provvisoria e la cambia al primo accesso; se la dimentica, il
  Responsabile gliene assegna una nuova. Minimo 10 caratteri, salvata con Argon2.
- **Amministratore di emergenza**: utente locale (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, password salvata
  con Argon2), creato al primo avvio. Serve quando l'AD non risponde.
- Sessione in cookie HttpOnly/Secure/SameSite=Strict, durata `JWT_MINUTI` con rinnovo automatico.
  Dopo 5 tentativi falliti l'utente resta bloccato 15 minuti (il Responsabile può sbloccarlo).
- Ruoli: **Responsabile** (tutto) e **Operatore** (le campagne dei suoi team, i contatti assegnati a
  lui e le sue opportunità). Ogni API controlla il ruolo lato server.

## Import del file Excel

Pagina **Importa dati** (solo Responsabile), in quattro passi:

1. si carica il file (`.xlsx`, `.xls` o `.csv`); le righe finiscono in una tabella di appoggio;
2. si abbinano le colonne ai campi del CRM (per il file attuale l'abbinamento è già proposto);
   le colonne senza campo si possono conservare come dato aggiuntivo (`extra`) o ignorare;
3. anteprima con righe scartate (manca cliente o veicolo) e avvisi (date o telefoni non validi,
   zero iniziale del fisso aggiunto);
4. conferma: i dati vanno nelle tabelle definitive e l'abbinamento si può salvare per i file successivi.

Regole: ogni riga è un veicolo; il cliente si riconosce dal **Cod. Cliente** (le righe dello stesso
cliente diventano un cliente con più veicoli); il veicolo dal telaio, poi dalla targa; il passaggio
in officina dal numero O.R. Una cella vuota non cancella un dato già presente.

## Campagne e chiamate

1. **Team**: il Responsabile raggruppa gli operatori in team; una persona può stare in più team.
2. **Campagne**: sceglie i veicoli con i filtri (marca, sede, date di immatricolazione e di ultimo
   passaggio, parole negli interventi), vede quanti sono e assegna la campagna a un team. Restano
   sempre fuori i clienti che non vogliono essere richiamati e, salvo diversa scelta, quelli senza
   telefono e i veicoli già in un'altra campagna attiva.
3. **Le mie chiamate**: i contatti stanno in una coda condivisa dal team. Con «Prossimo contatto»
   l'operatore ne prende uno, che da quel momento è suo: ognuno vede solo i propri. Prima dei
   contatti nuovi tornano i richiami arrivati a scadenza. Il Responsabile può riassegnarli.
4. **Esito**: a fine telefonata l'operatore sceglie l'esito, scrive una nota e, se serve, crea
   l'opportunità. L'esito decide cosa succede al contatto: resta da richiamare, esce dalla lista,
   oppure esce e il cliente non viene più richiamato da nessuna campagna.
5. **Opportunità**: appuntamento, sede, ammontare, vendita aggiuntiva e prodotto; ogni cambio di fase
   resta nello storico e per chiudere come persa serve il motivo.

Esiti, motivi di richiamo, fasi, motivi di perdita e prodotti si modificano dalla pagina **Elenchi**.

## Sviluppo

```sh
# backend
cd backend
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
export DATABASE_URL=postgresql+psycopg://crm:crm@localhost:5432/crm JWT_SECRET=dev COOKIE_SECURE=false ADMIN_PASSWORD=admin API_DOCS=true
alembic upgrade head && uvicorn app.main:app --reload

# test (serve un database vuoto dedicato)
TEST_DATABASE_URL=postgresql+psycopg://crm:crm@localhost:5432/crm_test pytest

# frontend (inoltra /api a localhost:8000)
cd frontend && npm install && npm run dev
```

Le modifiche al database passano da Alembic: `alembic revision --autogenerate -m "..."`.
