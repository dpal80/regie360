# CRM REGIE AUTO

CRM web per le chiamate di ricontatto dei clienti dell'officina e concessionaria REGIE AUTO.
Gira tutto in locale con Docker Compose: nessun servizio cloud esterno.

Questa è la **fase 1 (base)** del documento di architettura: login, utenti e ruoli, import
del file Excel con abbinamento delle colonne, anagrafica clienti e veicoli, registro attività.

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

### Portare il CRM sul server in sede (senza internet)

```sh
docker compose build
docker save crm-regie-auto-backend crm-regie-auto-proxy postgres:16-alpine | gzip > crm-immagini.tar.gz
# sul server: docker load < crm-immagini.tar.gz, poi copia docker-compose.yml e .env e lancia docker compose up -d
```

## Login

- **Utenti di dominio**: entrano con nome utente e password di Windows. Il backend verifica la password
  sull'Active Directory via LDAPS (`AD_SERVER`, `AD_DOMAIN`, eventualmente `AD_CA_FILE`).
  L'AD controlla solo la password: chi può entrare e con quale ruolo lo decide il Responsabile nella
  pagina **Utenti**. Un utente AD non aggiunto al CRM non entra.
- **Amministratore di emergenza**: utente locale (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, password salvata
  con Argon2), creato al primo avvio. Serve quando l'AD non risponde.
- Sessione in cookie HttpOnly/Secure/SameSite=Strict, durata `JWT_MINUTI` con rinnovo automatico.
  Dopo 5 tentativi falliti l'utente resta bloccato 15 minuti (il Responsabile può sbloccarlo).
- Ruoli: **Responsabile** (tutto) e **Operatore** (in questa fase vede solo la home; le liste di
  chiamata arrivano con la fase 2). Ogni API controlla il ruolo lato server.

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
