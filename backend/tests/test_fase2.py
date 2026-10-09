from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import security
from app.db import SessionLocal
from app.main import app
from app.models import Cliente, PassaggioOfficina, Utente, Veicolo
from app.security import hash_password


def crea_operatore(username: str) -> int:
    with SessionLocal() as db:
        u = Utente(username=username, nome=username.title(), ruolo="operatore", origine="locale",
                   password_hash=hash_password("password-operatore"), attivo=True)
        db.add(u)
        db.commit()
        return u.id


def entra(username: str) -> TestClient:
    c = TestClient(app, headers={"X-Requested-With": "crm"})
    assert c.post("/api/auth/login", json={"username": username, "password": "password-operatore"}).status_code == 200
    return c


def crea_veicolo(n: int, *, marca="RENAULT", telefono="3330000000", escluso=False, descrizione="TAGLIANDO") -> int:
    with SessionLocal() as db:
        c = Cliente(codice=str(n), nominativo=f"CLIENTE {n}", telefono_cellulare=telefono, escluso_richiami=escluso)
        v = Veicolo(cliente=c, targa=f"AA{n:03d}AA", telaio=f"TELAIO{n}", marca=marca, modello="CLIO",
                    data_immatricolazione=date(2022, 1, n))
        db.add_all([c, v])
        db.flush()
        db.add(PassaggioOfficina(veicolo_id=v.id, numero_or=str(n), descrizione=descrizione))
        db.commit()
        return v.id


def esito(client, nome: str) -> int:
    return next(v["id"] for v in client.get("/api/elenchi/esito").json() if v["nome"] == nome)


@pytest.fixture
def campagna(admin):
    """Tre veicoli, un team con due operatori e una campagna che li prende tutti."""
    for n in (1, 2, 3):
        crea_veicolo(n)
    op1, op2 = crea_operatore("op1"), crea_operatore("op2")
    crea_operatore("estraneo")
    team = admin.post("/api/team", json={"nome": "Viterbo", "membri": [op1, op2]}).json()
    r = admin.post("/api/campagne", json={"nome": "Tagliandi", "team_id": team["id"], "filtri": {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_ad_si_configura_dalla_pagina(admin, monkeypatch):
    assert admin.get("/api/impostazioni/ad").json()["origine"] == "file"
    r = admin.put("/api/impostazioni/ad", json={"server": "dc1.regie.local", "dominio": "REGIE.local"})
    assert r.status_code == 200, r.text
    letta = admin.get("/api/impostazioni/ad").json()
    assert letta["origine"] == "pagina" and letta["server"] == "dc1.regie.local" and letta["dominio"] == "regie.local"
    with SessionLocal() as db:
        assert security.config_ad(db).server == "dc1.regie.local"

    visti = {}

    def finta(username, password, cfg=None):
        visti["cfg"] = cfg
        return password == "giusta"

    monkeypatch.setattr("app.api.impostazioni.verifica_ad", finta)
    prova = {"server": "dc2.regie.local", "dominio": "regie.local", "username": "REGIE\\mario", "password": "giusta"}
    assert admin.post("/api/impostazioni/ad/prova", json=prova).json()["ok"] is True
    assert visti["cfg"].server == "dc2.regie.local"  # prova i dati del modulo, non quelli salvati
    assert admin.post("/api/impostazioni/ad/prova", json={**prova, "password": "no"}).json()["ok"] is False

    assert admin.put("/api/impostazioni/ad", json={"server": "x", "dominio": "y", "certificato_ca": "abc"}).status_code == 422
    assert admin.delete("/api/impostazioni/ad").json()["origine"] == "file"


def test_ad_solo_responsabile(admin):
    crea_operatore("op1")
    with entra("op1") as op:
        assert op.get("/api/impostazioni/ad").status_code == 403
        assert op.put("/api/impostazioni/ad", json={"server": "x", "dominio": "y"}).status_code == 403


def test_elenchi_predefiniti_e_modifica(admin):
    esiti = admin.get("/api/elenchi/esito").json()
    assert {"Non risponde", "Appuntamento preso"} <= {v["nome"] for v in esiti}
    assert admin.post("/api/elenchi/esito", json={"nome": "Segreteria"}).status_code == 422  # manca l'effetto
    r = admin.post("/api/elenchi/esito", json={"nome": "Segreteria", "effetto": "richiamo"})
    assert r.status_code == 201
    assert admin.post("/api/elenchi/esito", json={"nome": "Segreteria", "effetto": "richiamo"}).status_code == 409
    assert admin.patch(f"/api/elenchi/voci/{r.json()['id']}", json={"attivo": False}).status_code == 200
    assert "Segreteria" not in {v["nome"] for v in admin.get("/api/elenchi/esito").json()}
    assert "Segreteria" in {v["nome"] for v in admin.get("/api/elenchi/esito?tutte=true").json()}


def test_filtri_campagna(admin):
    crea_veicolo(1)
    crea_veicolo(2, marca="DACIA")
    crea_veicolo(3, telefono=None)
    crea_veicolo(4, escluso=True)
    crea_veicolo(5, descrizione="CARROZZERIA")
    anteprima = lambda f: admin.post("/api/campagne/anteprima", json=f).json()["veicoli"]  # noqa: E731
    assert anteprima({}) == 3  # fuori chi non ha telefono e chi si è opposto
    assert anteprima({"solo_con_telefono": False}) == 4
    assert anteprima({"marca": "DACIA"}) == 1
    assert anteprima({"parole": ["tagliando", "tga"]}) == 2
    assert anteprima({"immatricolazione_da": "2022-01-02", "immatricolazione_a": "2022-01-05"}) == 2

    team = admin.post("/api/team", json={"nome": "T"}).json()
    nuova = {"nome": "C", "team_id": team["id"], "filtri": {}}
    assert admin.post("/api/campagne", json=nuova).json()["totale"] == 3
    # i veicoli già in una campagna attiva non entrano in una seconda
    assert admin.post("/api/campagne", json=nuova).status_code == 422
    assert anteprima({"escludi_in_campagne_attive": False}) == 3


def test_coda_del_team(campagna):
    with entra("op1") as op1, entra("op2") as op2, entra("estraneo") as estraneo:
        assert estraneo.get("/api/campagne").json() == []
        assert estraneo.post(f"/api/campagne/{campagna['id']}/prossimo").status_code == 404
        assert op1.get("/api/campagne").json()[0]["in_coda"] == 3
        assert op1.get(f"/api/campagne/{campagna['id']}").status_code == 403

        primo = op1.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        # finché non lo chiama, "prossimo" gli ridà lo stesso contatto
        assert op1.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"] == primo
        secondo = op2.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        assert secondo != primo
        # ognuno vede solo i contatti assegnati a lui
        assert [c["id"] for c in op1.get("/api/contatti/miei").json()] == [primo]
        assert op2.get(f"/api/contatti/{primo}").status_code == 404
        assert op2.post(f"/api/contatti/{primo}/chiamate", json={"esito_id": esito(op2, "Non risponde")}).status_code == 404
        assert op1.get(f"/api/contatti/{primo}").json()["cliente_dati"]["nominativo"].startswith("CLIENTE")


def test_esiti_spostano_il_contatto(admin, campagna):
    with entra("op1") as op:
        cid = op.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        r = op.post(f"/api/contatti/{cid}/chiamate", json={
            "esito_id": esito(op, "Non risponde"), "nota": "Squilla a vuoto", "data_richiamo": "2030-01-01T10:00:00Z"})
        assert r.status_code == 201 and r.json()["stato"] == "richiamare"
        scheda = op.get(f"/api/contatti/{cid}").json()
        assert scheda["tentativi"] == 1 and scheda["note"][0]["testo"] == "Squilla a vuoto"
        assert len(scheda["chiamate"]) == 1
        # il richiamo è nel futuro: il prossimo contatto è un altro
        altro = op.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        assert altro != cid

        r = op.post(f"/api/contatti/{altro}/chiamate", json={"esito_id": esito(op, "Non vuole essere richiamato")})
        assert r.json()["stato"] == "chiuso"
        cliente_id = op.get(f"/api/contatti/{altro}").json()["cliente_id"]
        with SessionLocal() as db:
            assert db.get(Cliente, cliente_id).escluso_richiami is True

    stato = admin.get("/api/campagne").json()[0]
    assert (stato["da_chiamare"], stato["richiamare"], stato["chiusi"]) == (1, 1, 1)
    assert admin.patch(f"/api/campagne/{campagna['id']}", json={"stato": "chiusa"}).json()["stato"] == "chiusa"
    with entra("op1") as op:
        assert op.get("/api/campagne").json() == []
        assert op.post(f"/api/contatti/{cid}/chiamate", json={"esito_id": esito(op, "Non risponde")}).status_code == 400


def test_opportunita(admin, campagna):
    fasi = {v["nome"]: v["id"] for v in admin.get("/api/elenchi/fase_opportunita").json()}
    motivo = admin.get("/api/elenchi/motivo_perdita").json()[0]["id"]
    with entra("op1") as op1, entra("op2") as op2:
        cid = op1.post(f"/api/campagne/{campagna['id']}/prossimo").json()["contatto_id"]
        scheda = op1.get(f"/api/contatti/{cid}").json()
        chiamata = op1.post(f"/api/contatti/{cid}/chiamate", json={"esito_id": esito(op1, "Appuntamento preso")}).json()
        nuova = {"cliente_id": scheda["cliente_id"], "veicolo_id": scheda["veicolo_dati"]["id"],
                 "chiamata_id": chiamata["chiamata_id"], "data_appuntamento": "2030-02-01T09:00:00Z",
                 "descrizione": "Tagliando", "ammontare": "250.00"}
        # un operatore non crea opportunità su clienti che non sono suoi
        assert op2.post("/api/opportunita", json=nuova).status_code == 404
        r = op1.post("/api/opportunita", json=nuova)
        assert r.status_code == 201, r.text
        o = r.json()
        assert o["fase"] == "Appuntamento preso" and o["ammontare"] == 250.0
        assert op2.get("/api/opportunita").json()["totale"] == 0
        assert op2.patch(f"/api/opportunita/{o['id']}", json={"descrizione": "x"}).status_code == 404

        # per chiudere come persa serve il motivo
        assert op1.patch(f"/api/opportunita/{o['id']}", json={"fase_id": fasi["Chiusa persa"]}).status_code == 422
        r = op1.patch(f"/api/opportunita/{o['id']}", json={"fase_id": fasi["Chiusa persa"], "motivo_perdita_id": motivo})
        assert r.status_code == 200 and r.json()["fase_effetto"] == "persa"
        r = op1.patch(f"/api/opportunita/{o['id']}", json={"fase_id": fasi["Chiusa vinta"]})
        assert r.json()["motivo_perdita"] is None
    assert admin.get("/api/opportunita").json()["totale"] == 1
