import json

from app.db import SessionLocal
from app.models import Impostazione
from app.services import posta
from tests.test_fase2 import entra
from tests.test_superadmin import utente_locale

M365 = {"tenant_id": "11111111-2222-3333-4444-555555555555", "client_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        "mittente": "CRM@regieauto.it", "segreto": "segreto-app"}


def test_impostazioni_microsoft365(admin):
    utente_locale(admin, "capo", "responsabile")
    assert admin.get("/api/impostazioni/microsoft365").json()["segreto_presente"] is False
    assert admin.put("/api/impostazioni/microsoft365", json={**M365, "client_id": "non-un-guid"}).status_code == 422
    assert admin.put("/api/impostazioni/microsoft365", json={**M365, "mittente": "senza-chiocciola"}).status_code == 422
    assert admin.put("/api/impostazioni/microsoft365", json={**M365, "segreto": ""}).status_code == 422
    r = admin.put("/api/impostazioni/microsoft365", json=M365)
    assert r.status_code == 200, r.text
    # il segreto non torna mai indietro e nel database è cifrato
    assert r.json() == {"attivo": True, "tenant_id": M365["tenant_id"], "client_id": M365["client_id"],
                        "mittente": "crm@regieauto.it", "segreto_presente": True}
    with SessionLocal() as db:
        assert "segreto-app" not in json.dumps(db.get(Impostazione, "microsoft365").valore)
        assert posta.config_posta(db).segreto == "segreto-app"
    # salvare senza riscrivere il segreto tiene quello che c'è
    assert admin.put("/api/impostazioni/microsoft365", json={**M365, "segreto": "", "mittente": "altro@regieauto.it"}).status_code == 200
    with SessionLocal() as db:
        assert posta.config_posta(db).segreto == "segreto-app"
    with entra("capo") as resp:
        assert resp.get("/api/impostazioni/microsoft365").status_code == 403
        assert resp.post("/api/impostazioni/microsoft365/prova", json={"destinatario": "a@b.it"}).status_code == 403


def test_mail_di_prova(admin, monkeypatch):
    assert admin.post("/api/impostazioni/microsoft365/prova", json={"destinatario": "a@b.it"}).json()["ok"] is False
    admin.put("/api/impostazioni/microsoft365", json=M365)
    richieste = []

    def finta(url, *, dati, intestazioni):
        richieste.append((url, dati, intestazioni))
        if "oauth2" in url:
            return {"access_token": "token-graph"}
        return {}

    monkeypatch.setattr(posta, "_richiesta", finta)
    r = admin.post("/api/impostazioni/microsoft365/prova", json={"destinatario": "daniele@esempio.it"})
    assert r.json()["ok"] is True, r.text
    (url_token, dati_token, _), (url_invio, dati_invio, intestazioni) = richieste
    assert url_token == f"https://login.microsoftonline.com/{M365['tenant_id']}/oauth2/v2.0/token"
    assert b"client_secret=segreto-app" in dati_token and b"grant_type=client_credentials" in dati_token
    assert url_invio == "https://graph.microsoft.com/v1.0/users/crm%40regieauto.it/sendMail"
    assert intestazioni["Authorization"] == "Bearer token-graph"
    messaggio = json.loads(dati_invio)["message"]
    assert messaggio["toRecipients"] == [{"emailAddress": {"address": "daniele@esempio.it"}}]

    def rifiuta(url, *, dati, intestazioni):
        raise posta.PostaNonInviata("Microsoft ha risposto 401. Segreto scaduto")

    monkeypatch.setattr(posta, "_richiesta", rifiuta)
    r = admin.post("/api/impostazioni/microsoft365/prova", json={"destinatario": "daniele@esempio.it"}).json()
    assert r == {"ok": False, "messaggio": "Microsoft ha risposto 401. Segreto scaduto"}
