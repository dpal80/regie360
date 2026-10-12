import time

import pyotp
import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Utente
from app.services import posta
from tests.test_fase2 import crea_operatore, entra
from tests.test_posta import M365

PW = "password-operatore"


@pytest.fixture
def mail(admin, monkeypatch):
    """Posta configurata, con Microsoft simulato: le e-mail spedite finiscono in questa lista."""
    admin.put("/api/impostazioni/microsoft365", json=M365)
    spedite = []

    def finta(cfg, destinatari, oggetto, testo):
        if destinatari == ["rotta@esempio.it"]:
            raise posta.PostaNonInviata("Microsoft ha risposto 403.")
        spedite.append({"a": destinatari, "oggetto": oggetto, "testo": testo})

    monkeypatch.setattr(posta, "invia_mail", finta)
    return spedite


def anonimo() -> TestClient:
    return TestClient(app, headers={"X-Requested-With": "crm"})


def riga(testo: str, etichetta: str) -> str:
    return next(r.split(": ", 1)[1] for r in testo.splitlines() if r.startswith(etichetta))


def test_credenziali_provvisorie_per_email(admin, mail):
    nuovo = {"username": "giulia", "nome": "Giulia", "ruolo": "operatore", "origine": "locale",
             "email": "Giulia@Esempio.it", "invia_credenziali": True}
    assert admin.get("/api/impostazioni/microsoft365/stato").json() == {"attivo": True}
    r = admin.post("/api/utenti", json=nuovo)
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "giulia@esempio.it" and r.json()["deve_cambiare_password"] is True
    assert mail[0]["a"] == ["giulia@esempio.it"] and "giulia" in mail[0]["testo"]
    password = riga(mail[0]["testo"], "Password provvisoria")
    with anonimo() as c:
        assert c.post("/api/auth/login", json={"username": "giulia", "password": password}).status_code == 200
    # senza e-mail non si può, e se l'invio fallisce l'utente non viene creato
    assert admin.post("/api/utenti", json={**nuovo, "username": "altro", "email": ""}).status_code == 422
    assert admin.post("/api/utenti", json={**nuovo, "username": "altro", "email": "rotta@esempio.it"}).status_code == 502
    assert "altro" not in [u["username"] for u in admin.get("/api/utenti").json()]


def test_superadmin_reimposta_per_email(admin, mail):
    uid = crea_operatore("op1")
    assert admin.post(f"/api/utenti/{uid}/password", json={"invia": True}).status_code == 422  # senza e-mail
    assert admin.patch(f"/api/utenti/{uid}", json={"email": "rotta@esempio.it"}).status_code == 200
    assert admin.post(f"/api/utenti/{uid}/password", json={"invia": True}).status_code == 502
    with anonimo() as c:  # invio fallito: la password è rimasta quella di prima
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW}).status_code == 200
    admin.patch(f"/api/utenti/{uid}", json={"email": "op1@esempio.it"})
    r = admin.post(f"/api/utenti/{uid}/password", json={"invia": True})
    assert r.status_code == 200 and r.json()["deve_cambiare_password"] is True
    with anonimo() as c:
        nuova = riga(mail[-1]["testo"], "Password provvisoria")
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": nuova}).status_code == 200


def test_email_di_un_altro_la_cambia_solo_il_superadmin(admin):
    uid = crea_operatore("op1")
    capo = admin.post("/api/utenti", json={"username": "capo", "nome": "Capo", "ruolo": "responsabile",
                                           "origine": "locale", "password": PW}).json()["id"]
    with SessionLocal() as db:
        db.get(Utente, capo).deve_cambiare_password = False
        db.commit()
    with entra("capo") as resp:
        assert resp.patch(f"/api/utenti/{uid}", json={"email": "capo@esempio.it"}).status_code == 403
    with entra("op1") as op:  # la propria sì, confermando la password
        assert op.put("/api/auth/email", json={"email": "op1@esempio.it", "password": "sbagliata"}).status_code == 400
        assert op.put("/api/auth/email", json={"email": "non-valida", "password": PW}).status_code == 422
        assert op.put("/api/auth/email", json={"email": "op1@esempio.it", "password": PW}).json()["email"] == "op1@esempio.it"


def test_password_dimenticata(admin, mail):
    uid = crea_operatore("op1")
    with anonimo() as c:
        assert c.get("/api/auth/opzioni").json() == {"reset_password": True}
        # risposta identica per utenti inesistenti, senza e-mail o di dominio: nessun indizio
        for nome in ("op1", "non.esiste"):
            assert c.post("/api/auth/password-dimenticata", json={"username": nome}).status_code == 204
        assert mail == []
        admin.patch(f"/api/utenti/{uid}", json={"email": "op1@esempio.it"})
        assert c.post("/api/auth/password-dimenticata", json={"username": "OP1"}).status_code == 204
        assert len(mail) == 1
        codice = riga(mail[0]["testo"], "Codice")
        # una seconda richiesta subito dopo non manda un altro codice
        c.post("/api/auth/password-dimenticata", json={"username": "op1"})
        assert len(mail) == 1

        nuova = {"username": "op1", "nuova": "nuova-password-1"}
        assert c.post("/api/auth/password-reimposta", json={**nuova, "codice": "00000000"}).status_code == 400
        assert c.post("/api/auth/password-reimposta", json={**nuova, "codice": codice, "nuova": "corta"}).status_code == 422
        assert c.post("/api/auth/password-reimposta", json={**nuova, "codice": codice}).status_code == 204
        # il codice vale una volta sola
        assert c.post("/api/auth/password-reimposta", json={**nuova, "codice": codice}).status_code == 400
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": "nuova-password-1"}).status_code == 200


def test_codice_di_reset_si_brucia_dopo_5_errori(admin, mail):
    uid = crea_operatore("op1")
    admin.patch(f"/api/utenti/{uid}", json={"email": "op1@esempio.it"})
    with anonimo() as c:
        c.post("/api/auth/password-dimenticata", json={"username": "op1"})
        codice = riga(mail[0]["testo"], "Codice")
        sbagliato = "00000000" if codice != "00000000" else "11111111"
        for _ in range(5):
            assert c.post("/api/auth/password-reimposta", json={"username": "op1", "codice": sbagliato, "nuova": "nuova-password-1"}).status_code == 400
        assert c.post("/api/auth/password-reimposta", json={"username": "op1", "codice": codice, "nuova": "nuova-password-1"}).status_code == 400


def codice_di(segreto: str, sfasamento: int = 0) -> str:
    return pyotp.TOTP(segreto).at(time.time() + sfasamento * 30)


def test_verifica_in_due_passaggi(admin):
    uid = crea_operatore("op1")
    with entra("op1") as op:
        assert op.get("/api/auth/me").json()["totp_attivo"] is False
        avvio = op.post("/api/auth/2fa/avvia").json()
        assert avvio["qr_svg"].startswith("<svg") and len(avvio["segreto"]) >= 16
        # finché non conferma con un codice giusto non è attiva
        assert op.post("/api/auth/2fa/conferma", json={"codice": "000000"}).status_code == 400
        assert op.get("/api/auth/me").json()["totp_attivo"] is False
        assert op.post("/api/auth/2fa/conferma", json={"codice": codice_di(avvio["segreto"], -1)}).json()["totp_attivo"] is True
        segreto = avvio["segreto"]
    with SessionLocal() as db:
        assert segreto not in (db.get(Utente, uid).totp_segreto_cifrato or "")

    with anonimo() as c:
        # la sola password non basta più: il server chiede il codice e non apre la sessione
        r = c.post("/api/auth/login", json={"username": "op1", "password": PW})
        assert r.status_code == 401 and r.json()["detail"]["codice_richiesto"] is True
        assert c.get("/api/auth/me").status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": "000000"}).status_code == 401
        buono = codice_di(segreto)
        assert c.post("/api/auth/login", json={"username": "op1", "password": "sbagliata", "codice": buono}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": buono}).status_code == 200
        c.post("/api/auth/logout")
        # lo stesso codice non vale una seconda volta
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": buono}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": codice_di(segreto, 1)}).status_code == 200
        assert c.post("/api/auth/2fa/disattiva", json={"codice": "000000"}).status_code == 400

    # chi perde il telefono: il super-admin azzera, e si rientra con la sola password
    assert admin.get("/api/utenti").json()[-1]["totp_attivo"] in (True, False)
    assert admin.post(f"/api/utenti/{uid}/2fa/azzera").json()["totp_attivo"] is False
    with anonimo() as c:
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW}).status_code == 200


def test_codici_sbagliati_bloccano_come_le_password(admin):
    crea_operatore("op1")
    with entra("op1") as op:
        segreto = op.post("/api/auth/2fa/avvia").json()["segreto"]
        op.post("/api/auth/2fa/conferma", json={"codice": codice_di(segreto)})
    with anonimo() as c:
        for _ in range(5):
            assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": "000000"}).status_code == 401
        assert c.post("/api/auth/login", json={"username": "op1", "password": PW, "codice": codice_di(segreto, 1)}).status_code == 429


def test_2fa_degli_altri_solo_superadmin(admin):
    uid = crea_operatore("op1")
    crea_operatore("op2")
    with entra("op2") as altro:
        assert altro.post(f"/api/utenti/{uid}/2fa/azzera").status_code == 403
    io = admin.get("/api/auth/me").json()["id"]
    assert admin.post(f"/api/utenti/{io}/2fa/azzera").status_code == 400  # l'amministratore globale non si tocca
