from tests.test_fase2 import crea_operatore, entra

AD = {"server": "dc1.regie.local", "dominio": "regie.local"}
NETHVOICE = {"cti_host": "cti.regie.local", "sip_host": "sip.regie.local", "sip_porta": "5061"}


def utente_locale(admin, username: str, ruolo: str) -> int:
    r = admin.post("/api/utenti", json={"username": username, "nome": username, "ruolo": ruolo,
                                        "origine": "locale", "password": "password-operatore"})
    assert r.status_code == 201, r.text
    # nei test si salta il cambio password al primo accesso
    from app.db import SessionLocal
    from app.models import Utente

    with SessionLocal() as db:
        db.get(Utente, r.json()["id"]).deve_cambiare_password = False
        db.commit()
    return r.json()["id"]


def test_responsabile_gestisce_ruoli_ma_non_password_e_sistema(admin):
    capo = utente_locale(admin, "capo", "responsabile")
    op = crea_operatore("op1")
    with entra("capo") as resp:
        # resta tutto quello che faceva: aggiunge utenti, assegna i ruoli, vede campagne e anagrafica
        assert resp.post("/api/utenti", json={"username": "mario.rossi", "nome": "Mario", "ruolo": "operatore"}).status_code == 201
        assert resp.patch(f"/api/utenti/{op}", json={"ruolo": "responsabile"}).status_code == 200
        assert resp.get("/api/campagne").status_code == 200
        assert resp.get("/api/clienti").status_code == 200
        # le password degli altri e i collegamenti di sistema sono del super-admin
        assert resp.post(f"/api/utenti/{op}/password", json={"password": "nuova-provvisoria"}).status_code == 403
        assert resp.get("/api/impostazioni/ad").status_code == 403
        assert resp.put("/api/impostazioni/ad", json=AD).status_code == 403
        assert resp.put("/api/impostazioni/nethvoice", json=NETHVOICE).status_code == 403
        # non può nominare super-admin né toccare un super-admin
        assert resp.patch(f"/api/utenti/{op}", json={"ruolo": "superadmin"}).status_code == 403
        assert resp.post("/api/utenti", json={"username": "x", "nome": "X", "ruolo": "superadmin"}).status_code == 403
        admin_id = admin.get("/api/auth/me").json()["id"]
        assert resp.patch(f"/api/utenti/{admin_id}", json={"nome": "Altro"}).status_code == 403
    assert capo


def test_altri_utenti_possono_essere_superadmin(admin):
    capo = utente_locale(admin, "capo", "responsabile")
    op = crea_operatore("op1")
    assert admin.patch(f"/api/utenti/{capo}", json={"ruolo": "superadmin"}).json()["ruolo"] == "superadmin"
    with entra("capo") as nuovo:
        # il nuovo super-admin cambia la password di un utente locale...
        r = nuovo.post(f"/api/utenti/{op}/password", json={"password": "nuova-provvisoria"})
        assert r.status_code == 200 and r.json()["deve_cambiare_password"] is True
        assert nuovo.put("/api/impostazioni/ad", json=AD).status_code == 200
        assert nuovo.put("/api/impostazioni/nethvoice", json=NETHVOICE).status_code == 200
        # ...ma di un utente di dominio può solo assegnare il ruolo
        r = nuovo.post("/api/utenti", json={"username": "mario.rossi", "nome": "Mario", "ruolo": "operatore"})
        dominio = r.json()["id"]
        assert nuovo.post(f"/api/utenti/{dominio}/password", json={"password": "nuova-provvisoria"}).status_code == 400
        assert nuovo.patch(f"/api/utenti/{dominio}", json={"ruolo": "responsabile"}).json()["ruolo"] == "responsabile"
        # resta anche Responsabile a tutti gli effetti
        assert nuovo.get("/api/campagne").status_code == 200
        assert nuovo.post("/api/team", json={"nome": "T"}).status_code == 201


def test_amministratore_globale_non_si_modifica(admin):
    capo = utente_locale(admin, "capo", "superadmin")
    io = admin.get("/api/auth/me").json()
    assert io["ruolo"] == "admin_globale"
    # il ruolo è solo suo: non si assegna ad altri
    assert admin.patch(f"/api/utenti/{capo}", json={"ruolo": "admin_globale"}).status_code == 422
    assert admin.post("/api/utenti", json={"username": "x", "nome": "X", "ruolo": "admin_globale"}).status_code == 422
    with entra("capo") as altro:
        # nemmeno un super-admin può toccarlo
        for modifica in ({"nome": "Altro"}, {"ruolo": "operatore"}, {"attivo": False}, {"interno": "9"}):
            assert altro.patch(f"/api/utenti/{io['id']}", json=modifica).status_code == 400
        assert altro.post(f"/api/utenti/{io['id']}/password", json={"password": "nuova-provvisoria"}).status_code == 400
    assert admin.patch(f"/api/utenti/{io['id']}", json={"nome": "Altro"}).status_code == 400
    # resta super-admin e Responsabile a tutti gli effetti, e cambia da solo la propria password
    assert admin.get("/api/impostazioni/ad").status_code == 200
    assert admin.get("/api/campagne").status_code == 200
    r = admin.post("/api/auth/password", json={"attuale": "password-admin-di-prova", "nuova": "nuova-password-admin"})
    assert r.status_code == 204
