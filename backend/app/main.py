import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert

from app.api import (
    anagrafica,
    auth,
    campagne,
    elenchi,
    importazioni,
    impostazioni,
    opportunita,
    team,
    telefonia,
    utenti,
)
from app.config import get_settings
from app.db import SessionLocal
from app.models import ORIGINE_LOCALE, RUOLO_SUPERADMIN, Utente
from app.security import hash_password, normalizza_username

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("crm")


@asynccontextmanager
async def lifespan(_: FastAPI):
    crea_admin_emergenza()
    elenchi.crea_elenchi_predefiniti()
    yield


app = FastAPI(
    title="Regie360",
    docs_url="/api/docs" if get_settings().api_docs else None,
    openapi_url="/api/openapi.json" if get_settings().api_docs else None,
    redoc_url=None,
    lifespan=lifespan,
)

METODI_SICURI = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def protezione_csrf(request: Request, call_next):
    """Le richieste che modificano dati devono arrivare dal frontend del CRM.

    Oltre al cookie SameSite=Strict, serve l'intestazione X-Requested-With, che un altro
    sito non può aggiungere senza un permesso CORS (che il backend non concede).
    """
    if request.method not in METODI_SICURI and request.url.path.startswith("/api/"):
        if request.headers.get("x-requested-with") != "crm":
            return JSONResponse({"detail": "Richiesta non valida"}, status_code=403)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


for r in (
    auth.router, utenti.router, importazioni.router, anagrafica.router, impostazioni.router,
    team.router, elenchi.router, campagne.router, opportunita.router, telefonia.router,
):
    app.include_router(r, prefix="/api")


@app.get("/api/salute")
def salute():
    return {"stato": "ok"}


def crea_admin_emergenza() -> None:
    """Crea l'amministratore locale al primo avvio, se è impostata ADMIN_PASSWORD."""
    s = get_settings()
    if not s.admin_password:
        return
    username = normalizza_username(s.admin_username)
    # Con più processi in parallelo l'insert può arrivare due volte: il secondo non fa nulla.
    with SessionLocal() as db:
        creato = db.execute(
            insert(Utente)
            .values(
                username=username,
                nome="Amministratore di emergenza",
                ruolo=RUOLO_SUPERADMIN,
                origine=ORIGINE_LOCALE,
                password_hash=hash_password(s.admin_password),
                attivo=True,
                tentativi_falliti=0,
            )
            .on_conflict_do_nothing(index_elements=["username"])
            .returning(Utente.id)
        ).scalar()
        # Un amministratore di emergenza creato prima che esistesse il super-admin viene promosso.
        db.execute(
            update(Utente)
            .where(Utente.username == username, Utente.origine == ORIGINE_LOCALE,
                   Utente.ruolo != RUOLO_SUPERADMIN)
            .values(ruolo=RUOLO_SUPERADMIN)
        )
        db.commit()
    if creato:
        log.info("Creato l'amministratore locale '%s'", username)
