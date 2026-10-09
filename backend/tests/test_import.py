from app.services.importa import _data, _telefono, controlla_mappatura, leggi_file, suggerisci_mappatura
from tests.conftest import INTESTAZIONI, crea_xlsx, riga


def test_telefoni():
    assert _telefono(3474675576) == ("3474675576", None)
    assert _telefono("+39 347 467 5576") == ("3474675576", None)
    assert _telefono("0761 123456") == ("0761123456", None)
    numero, avviso = _telefono(7661358)
    assert numero == "07661358" and "0 iniziale" in avviso
    assert _telefono("abc")[0] is None
    assert _telefono(None) == (None, None)


def test_date():
    assert str(_data("2020-01-10")) == "2020-01-10"
    assert str(_data("10/01/2020")) == "2020-01-10"
    assert str(_data(43840)) == "2020-01-10"  # numero seriale Excel


def test_mappatura_suggerita_sul_file_regie():
    m = dict(zip(INTESTAZIONI, suggerisci_mappatura(INTESTAZIONI), strict=True))
    assert m["Cod. Cliente"] == "cliente.codice"
    assert m["Tel. Domicilio"] == "cliente.telefono_fisso"
    assert m["N° O.R./Pratica"] == "passaggio.numero_or"
    assert m["Servizio"] == "passaggio.sede"
    assert m["caller"] == "ignora"
    assert controlla_mappatura(INTESTAZIONI, list(m.values())) == []


def test_mappatura_senza_veicolo():
    errori = controlla_mappatura(["Cod. Cliente"], ["cliente.codice"])
    assert any("veicolo" in e for e in errori)


def test_lettura_xlsx_tiene_numero_riga():
    intestazioni, righe = leggi_file(crea_xlsx([riga(), [None] * 19, riga(Targa="BB222BB")]))
    assert intestazioni == INTESTAZIONI
    assert [n for n, _ in righe] == [2, 4]
    assert righe[0][1][9] == 1001


def _importa(client, contenuto, salva_come=None):
    r = client.post("/api/importazioni", files={"file": ("clienti.xlsx", contenuto)})
    assert r.status_code == 201, r.text
    imp = r.json()
    a = client.post(f"/api/importazioni/{imp['id']}/anteprima", json={"mappatura": imp["mappatura"]})
    assert a.status_code == 200, a.text
    c = client.post(
        f"/api/importazioni/{imp['id']}/conferma",
        json={"mappatura": imp["mappatura"], "salva_come": salva_come},
    )
    assert c.status_code == 200, c.text
    return imp, a.json(), c.json()


def test_import_completo(admin):
    file = crea_xlsx([
        riga(),
        # stesso cliente, secondo veicolo, fisso senza zero
        riga(Targa="BB222BB", Telaio="VF1TEST0000000002", **{"N° O.R./Pratica": 5002, "Tel. Domicilio": 7661358}),
        # riga senza targa né telaio: scartata
        riga(Targa=None, Telaio=None, **{"Cod. Cliente": 2002, "N° O.R./Pratica": 5003}),
        riga(Targa="CC333CC", Telaio="VF1TEST0000000003", Cognome="BIANCHI SRL", Marca="dacia",
             **{"Cod. Cliente": 3003, "N° O.R./Pratica": 5004, "Servizio": "Officina Renault CIVITAVECCHIA"}),
    ])
    imp, anteprima, esito = _importa(admin, file, salva_come="Export officina")

    assert anteprima["righe_totali"] == 4
    assert anteprima["righe_scartate"] == 1
    assert anteprima["clienti_distinti"] == 2
    assert any(p["riga"] == 4 and p["tipo"] == "errore" for p in anteprima["problemi"])

    assert esito["clienti_nuovi"] == 2
    assert esito["veicoli_nuovi"] == 3
    assert esito["passaggi_nuovi"] == 3
    assert esito["righe_scartate"] == 1

    clienti = admin.get("/api/clienti").json()
    assert clienti["totale"] == 2
    rossi = next(c for c in clienti["elementi"] if c["codice"] == "1001")
    assert rossi["num_veicoli"] == 2
    assert rossi["telefono_fisso"] == "07661358"

    dettaglio = admin.get(f"/api/clienti/{rossi['id']}").json()
    assert {v["targa"] for v in dettaglio["veicoli"]} == {"AA111AA", "BB222BB"}
    assert dettaglio["veicoli"][0]["passaggi"][0]["sede"] == "Officina Renault VITERBO"

    veicoli = admin.get("/api/veicoli", params={"marca": "DACIA"}).json()
    assert veicoli["totale"] == 1
    assert veicoli["elementi"][0]["data_ultimo_passaggio"] == "2021-01-05"
    assert len(admin.get("/api/sedi").json()) == 2

    # Ricaricando lo stesso file non si crea nulla di nuovo e si riusa la mappatura salvata.
    r = admin.post("/api/importazioni", files={"file": ("clienti.xlsx", file)})
    assert r.json()["mappatura_salvata"] == "Export officina"
    _, _, esito2 = _importa(admin, file)
    assert esito2["clienti_nuovi"] == 0 and esito2["veicoli_nuovi"] == 0 and esito2["passaggi_nuovi"] == 0
    assert admin.get("/api/clienti").json()["totale"] == 2


def test_cella_vuota_non_cancella_dato(admin):
    _importa(admin, crea_xlsx([riga()]))
    _importa(admin, crea_xlsx([riga(**{"e-mail": None, "N° O.R./Pratica": 6001})]))
    c = admin.get("/api/clienti").json()["elementi"][0]
    assert c["email"] == "mario@esempio.it"


def test_file_non_valido(admin):
    r = admin.post("/api/importazioni", files={"file": ("x.xlsx", b"PK\x03\x04rotto")})
    assert r.status_code == 422


def test_mappatura_errata_rifiutata(admin):
    imp = admin.post("/api/importazioni", files={"file": ("c.xlsx", crea_xlsx([riga()]))}).json()
    m = ["ignora"] * len(imp["intestazioni"])
    r = admin.post(f"/api/importazioni/{imp['id']}/anteprima", json={"mappatura": m})
    assert r.status_code == 422
    assert admin.delete(f"/api/importazioni/{imp['id']}").status_code == 204
    assert admin.get("/api/importazioni").json() == []
