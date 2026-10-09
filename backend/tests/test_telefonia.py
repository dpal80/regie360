import base64

import pytest

from app.db import SessionLocal
from app.models import Chiamata, Utente
from app.services import telefonia
from tests.conftest import crea_utente_ad
from tests.test_fase2 import crea_operatore, crea_veicolo, entra, esito

NETHVOICE = {"cti_host": "https://CTI.regie.local/", "sip_host": "sip.regie.local", "sip_porta": "5061"}


@pytest.fixture
def nethvoice(monkeypatch):
    """Simula la CTI di NethVoice: password giusta = 'giusta', l'utente 'senza.web' non ha il telefono web."""
    chiamate = []

    def finta(cfg, metodo, percorso, *, token=None, dati=None):
        chiamate.append((metodo, percorso))
        if percorso == "/login":
            if dati["password"] != "giusta":
                raise telefonia.CredenzialiRifiutate()
            return {"code": 200, "token": f"sessione-{dati['username']}"}
        assert token.startswith("sessione-")
        utente = token.removeprefix("sessione-")
        if percorso == "/user/me":
            interni = [{"id": "211", "type": "physical", "secret": "x"}]
            if utente != "senza.web":
                interni.append({"id": "92211", "type": "webrtc", "secret": "segreto-sip"})
            return {"username": utente, "endpoints": {"extension": interni}}
        if percorso == "/tokens/persistent/phone-island":
            return {"token": "token-phone-island"}
        return {}

    monkeypatch.setattr(telefonia, "_chiama", finta)
    return chiamate


def test_impostazioni_nethvoice(admin):
    crea_operatore("op1")
    assert admin.get("/api/telefonia/stato").json() == {"attivo": False, "collegato": False, "interno": None, "data_config": None}
    assert admin.put("/api/impostazioni/nethvoice", json={**NETHVOICE, "cti_host": "cti/percorso"}).status_code == 422
    assert admin.put("/api/impostazioni/nethvoice", json={**NETHVOICE, "sip_porta": "abc"}).status_code == 422
    r = admin.put("/api/impostazioni/nethvoice", json=NETHVOICE)
    assert r.status_code == 200 and r.json()["cti_host"] == "cti.regie.local"
    assert admin.get("/api/telefonia/stato").json()["attivo"] is True
    with entra("op1") as op:
        assert op.get("/api/impostazioni/nethvoice").status_code == 403
        assert op.put("/api/impostazioni/nethvoice", json=NETHVOICE).status_code == 403


def test_collega_telefono(admin, nethvoice):
    crea_operatore("op1")
    with entra("op1") as op:
        assert op.post("/api/telefonia/collega", json={"password": "giusta"}).status_code == 400  # non configurata
        admin.put("/api/impostazioni/nethvoice", json=NETHVOICE)
        assert op.post("/api/telefonia/collega", json={"password": "sbagliata"}).status_code == 400
        assert op.post("/api/telefonia/collega", json={"username": "senza.web", "password": "giusta"}).status_code == 400
        r = op.post("/api/telefonia/collega", json={"password": "giusta"})
        assert r.status_code == 200, r.text
        assert r.json()["interno"] == "92211"
        campi = base64.b64decode(op.get("/api/telefonia/stato").json()["data_config"]).decode().split(":")
        assert campi == ["cti.regie.local", "op1", "token-phone-island", "92211", "segreto-sip", "sip.regie.local", "5061"]
        # la sessione aperta su NethVoice per chiedere il token viene chiusa
        assert nethvoice[-1] == ("POST", "/logout")
        # nel database il segreto è cifrato
        with SessionLocal() as db:
            salvato = db.query(Utente).filter_by(username="op1").one().telefono_cifrato
        assert salvato and "segreto-sip" not in salvato and "token-phone-island" not in salvato
        # un altro utente non vede il telefono di op1
        assert admin.get("/api/telefonia/stato").json()["collegato"] is False
        assert op.delete("/api/telefonia/collega").json()["collegato"] is False


def test_login_di_dominio_collega_il_telefono(admin, nethvoice, ad_finto):
    admin.put("/api/impostazioni/nethvoice", json=NETHVOICE)
    crea_utente_ad("mario.rossi", "operatore")
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, headers={"X-Requested-With": "crm"}) as op:
        assert op.post("/api/auth/login", json={"username": "mario.rossi", "password": "giusta"}).status_code == 200
        assert op.get("/api/telefonia/stato").json()["interno"] == "92211"
        prima = len(nethvoice)
        # al secondo accesso il token c'è già: NethVoice non viene richiamato (un token nuovo revocherebbe il vecchio)
        assert op.post("/api/auth/login", json={"username": "mario.rossi", "password": "giusta"}).status_code == 200
        assert len(nethvoice) == prima


def test_login_va_avanti_se_nethvoice_non_risponde(admin, ad_finto, monkeypatch):
    admin.put("/api/impostazioni/nethvoice", json=NETHVOICE)
    crea_utente_ad("mario.rossi", "operatore")

    def spento(*a, **k):
        raise telefonia.NethVoiceNonRaggiungibile("spento")

    monkeypatch.setattr(telefonia, "_chiama", spento)
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, headers={"X-Requested-With": "crm"}) as op:
        assert op.post("/api/auth/login", json={"username": "mario.rossi", "password": "giusta"}).status_code == 200
        assert op.get("/api/telefonia/stato").json()["collegato"] is False


def test_chi_sta_chiamando_e_id_chiamata(admin):
    crea_veicolo(1, telefono="333 1234567")
    op1 = crea_operatore("op1")
    crea_operatore("op2")
    team = admin.post("/api/team", json={"nome": "T", "membri": [op1]}).json()
    campagna = admin.post("/api/campagne", json={"nome": "C", "team_id": team["id"], "filtri": {}}).json()
    assert admin.get("/api/telefonia/cerca?numero=123").json() == {"clienti": []}
    trovato = admin.get("/api/telefonia/cerca?numero=%2B393331234567").json()["clienti"][0]
    assert trovato["nominativo"] == "CLIENTE 1" and trovato["cliente_id"]
    with entra("op1") as op, entra("op2") as altro:
        cid = op.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        assert op.get("/api/telefonia/cerca?numero=3331234567").json()["clienti"] == [
            {"nominativo": "CLIENTE 1", "cliente_id": None, "contatto_id": cid}]
        assert altro.get("/api/telefonia/cerca?numero=3331234567").json()["clienti"][0]["contatto_id"] is None
        r = op.post(f"/api/contatti/{cid}/chiamate", json={
            "esito_id": esito(op, "Non risponde"), "unique_id": "1671557974.4929", "durata_secondi": 42})
        with SessionLocal() as db:
            c = db.get(Chiamata, r.json()["chiamata_id"])
            assert (c.unique_id, c.durata_secondi) == ("1671557974.4929", 42)
