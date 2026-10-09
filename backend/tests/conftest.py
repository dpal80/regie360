import io
import os
from datetime import datetime

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://crm:crm@localhost:5432/crm_test"),
)
os.environ["JWT_SECRET"] = "test-secret-con-almeno-32-caratteri!!"
os.environ["COOKIE_SECURE"] = "false"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "password-admin-di-prova"
os.environ["AD_SERVER"] = "ad.esempio.local"
os.environ["AD_DOMAIN"] = "esempio.local"

from fastapi.testclient import TestClient  # noqa: E402

from app import security  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import ORIGINE_AD, Utente  # noqa: E402

INTESTAZIONI = [
    "Immatricolazione", "Targa", "Telaio", "Cognome", "Nome", "Marca", "e-mail",
    "Tel. Cellulare", "Tel. Domicilio", "Cod. Cliente", "Intervento - Richiesta Cliente",
    "Servizio", "Modello", "N° O.R./Pratica", "Data Creaz.", "Data Emis.",
    "data chiamata", "caller", "app preso",
]


def riga(**k):
    base = {
        "Immatricolazione": datetime(2020, 1, 10), "Targa": "AA111AA", "Telaio": "VF1TEST0000000001",
        "Cognome": "ROSSI MARIO", "Nome": None, "Marca": "RENAULT", "e-mail": "mario@esempio.it",
        "Tel. Cellulare": 3331234567, "Tel. Domicilio": None, "Cod. Cliente": 1001,
        "Intervento - Richiesta Cliente": "R_CLT TAGLIANDO", "Servizio": "Officina Renault VITERBO",
        "Modello": "CLIO", "N° O.R./Pratica": 5001, "Data Creaz.": datetime(2021, 1, 4),
        "Data Emis.": datetime(2021, 1, 5), "data chiamata": None, "caller": None, "app preso": None,
    }
    base.update(k)
    return [base[h] for h in INTESTAZIONI]


def crea_xlsx(righe: list[list]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(INTESTAZIONI)
    for r in righe:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app, headers={"X-Requested-With": "crm"}) as c:
        yield c


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "password-admin-di-prova"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def ad_finto(monkeypatch):
    """Simula l'Active Directory: password giusta = 'giusta'."""
    monkeypatch.setattr(security, "verifica_ad", lambda u, p: p == "giusta")


def crea_utente_ad(username: str, ruolo: str) -> None:
    with SessionLocal() as db:
        db.add(Utente(username=username, nome=username.title(), ruolo=ruolo, origine=ORIGINE_AD, attivo=True))
        db.commit()
