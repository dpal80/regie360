from tests.conftest import crea_utente_ad


def test_admin_locale_entra(admin):
    r = admin.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["ruolo"] == "responsabile"
    assert r.json()["origine"] == "locale"


def test_password_sbagliata(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "no"})
    assert r.status_code == 401


def test_blocco_dopo_5_tentativi(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "no"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "admin", "password": "password-admin-di-prova"})
    assert r.status_code == 429


def test_utente_ad_non_abilitato_nel_crm(client, ad_finto):
    r = client.post("/api/auth/login", json={"username": "mario.rossi", "password": "giusta"})
    assert r.status_code == 401


def test_utente_ad_abilitato(client, ad_finto):
    crea_utente_ad("mario.rossi", "operatore")
    r = client.post("/api/auth/login", json={"username": "REGIE\\Mario.Rossi", "password": "giusta"})
    assert r.status_code == 200
    assert r.json()["username"] == "mario.rossi"
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").status_code == 401


def test_password_vuota_non_passa_mai(client):
    # Su AD un bind con password vuota riesce come anonimo: va rifiutato prima.
    from app.security import verifica_ad

    assert verifica_ad("chiunque", "") is False


def test_operatore_non_gestisce_utenti(client, ad_finto):
    crea_utente_ad("op1", "operatore")
    client.post("/api/auth/login", json={"username": "op1", "password": "giusta"})
    assert client.get("/api/utenti").status_code == 403
    assert client.get("/api/clienti").status_code == 403


def test_utente_disattivato_esce_subito(admin, ad_finto):
    r = admin.post("/api/utenti", json={"username": "op2", "nome": "Operatrice Due", "ruolo": "operatore"})
    assert r.status_code == 201
    uid = r.json()["id"]

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, headers={"X-Requested-With": "crm"}) as op:
        assert op.post("/api/auth/login", json={"username": "op2", "password": "giusta"}).status_code == 200
        assert admin.patch(f"/api/utenti/{uid}", json={"attivo": False}).status_code == 200
        assert op.get("/api/auth/me").status_code == 401


def test_serve_intestazione_csrf(client):
    r = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "password-admin-di-prova"},
        headers={"X-Requested-With": ""},
    )
    assert r.status_code == 403


def test_admin_non_si_disattiva(admin):
    me = admin.get("/api/auth/me").json()
    assert admin.patch(f"/api/utenti/{me['id']}", json={"attivo": False}).status_code == 400
