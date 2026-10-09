import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, formatoData, post, type Campagna, type Voce } from "../api";

type Team = { id: number; nome: string; attivo: boolean; membri: unknown[] };
type Anteprima = {
  veicoli: number;
  clienti: number;
  esempi: { targa: string | null; veicolo: string; cliente: string; data_immatricolazione: string | null; data_ultimo_passaggio: string | null }[];
};

const FILTRI_VUOTI = {
  marca: "",
  sede_id: "",
  immatricolazione_da: "",
  immatricolazione_a: "",
  ultimo_passaggio_da: "",
  ultimo_passaggio_a: "",
  parole: "",
  solo_con_telefono: true,
  escludi_in_campagne_attive: true,
};

export default function Campagne() {
  const [campagne, setCampagne] = useState<Campagna[]>([]);
  const [team, setTeam] = useState<Team[]>([]);
  const [motivi, setMotivi] = useState<Voce[]>([]);
  const [marche, setMarche] = useState<string[]>([]);
  const [sedi, setSedi] = useState<{ id: number; nome: string }[]>([]);
  const [aperto, setAperto] = useState(false);
  const [nuova, setNuova] = useState({ nome: "", motivo_id: "", team_id: "" });
  const [filtri, setFiltri] = useState(FILTRI_VUOTI);
  const [anteprima, setAnteprima] = useState<Anteprima | null>(null);
  const [errore, setErrore] = useState("");

  const carica = () => api<Campagna[]>("/campagne").then(setCampagne).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
    api<Team[]>("/team").then((t) => setTeam(t.filter((x) => x.attivo))).catch(() => undefined);
    api<Voce[]>("/elenchi/motivo_richiamo").then(setMotivi).catch(() => undefined);
    api<string[]>("/marche").then(setMarche).catch(() => undefined);
    api<{ id: number; nome: string }[]>("/sedi").then(setSedi).catch(() => undefined);
  }, []);

  const imposta = (k: keyof typeof filtri) => (e: { target: { value: string } }) => {
    setFiltri({ ...filtri, [k]: e.target.value });
    setAnteprima(null);
  };
  const spunta = (k: keyof typeof filtri) => (e: { target: { checked: boolean } }) => {
    setFiltri({ ...filtri, [k]: e.target.checked });
    setAnteprima(null);
  };

  const filtriApi = () => ({
    marca: filtri.marca || null,
    sede_id: filtri.sede_id ? Number(filtri.sede_id) : null,
    immatricolazione_da: filtri.immatricolazione_da || null,
    immatricolazione_a: filtri.immatricolazione_a || null,
    ultimo_passaggio_da: filtri.ultimo_passaggio_da || null,
    ultimo_passaggio_a: filtri.ultimo_passaggio_a || null,
    parole: filtri.parole.split(",").map((p) => p.trim()).filter(Boolean),
    solo_con_telefono: filtri.solo_con_telefono,
    escludi_in_campagne_attive: filtri.escludi_in_campagne_attive,
  });

  async function esegui(f: () => Promise<void>) {
    setErrore("");
    try {
      await f();
    } catch (e) {
      setErrore((e as Error).message);
    }
  }

  const calcola = () => esegui(async () => setAnteprima(await post<Anteprima>("/campagne/anteprima", filtriApi())));

  function crea(e: FormEvent) {
    e.preventDefault();
    esegui(async () => {
      await post("/campagne", {
        nome: nuova.nome,
        motivo_id: nuova.motivo_id ? Number(nuova.motivo_id) : null,
        team_id: Number(nuova.team_id),
        filtri: filtriApi(),
      });
      setNuova({ nome: "", motivo_id: "", team_id: "" });
      setFiltri(FILTRI_VUOTI);
      setAnteprima(null);
      setAperto(false);
      await carica();
    });
  }

  return (
    <>
      <div className="testata">
        <h1>Campagne</h1>
        {!aperto && <button className="primario" onClick={() => setAperto(true)}>Nuova campagna</button>}
      </div>
      {errore && <div className="errore">{errore}</div>}
      {aperto && (
        <form className="scheda" onSubmit={crea}>
          <h3>Nuova campagna</h3>
          {team.length === 0 && (
            <div className="errore">Prima di creare una campagna serve almeno un team: crealo nella pagina <Link to="/team">Team</Link>.</div>
          )}
          <div className="filtri">
            <label>Nome<input required value={nuova.nome} onChange={(e) => setNuova({ ...nuova, nome: e.target.value })} placeholder="Tagliandi marzo" /></label>
            <label>
              Motivo
              <select value={nuova.motivo_id} onChange={(e) => setNuova({ ...nuova, motivo_id: e.target.value })}>
                <option value="">Nessuno</option>
                {motivi.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
              </select>
            </label>
            <label>
              Team
              <select required value={nuova.team_id} onChange={(e) => setNuova({ ...nuova, team_id: e.target.value })}>
                <option value="">Scegli…</option>
                {team.map((t) => <option key={t.id} value={t.id}>{t.nome} ({t.membri.length})</option>)}
              </select>
            </label>
          </div>
          <h3>Quali veicoli richiamare</h3>
          <div className="filtri">
            <label>
              Marca
              <select value={filtri.marca} onChange={imposta("marca")}>
                <option value="">Tutte</option>
                {marche.map((m) => <option key={m}>{m}</option>)}
              </select>
            </label>
            <label>
              Sede
              <select value={filtri.sede_id} onChange={imposta("sede_id")}>
                <option value="">Tutte</option>
                {sedi.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
              </select>
            </label>
            <label>Immatricolata dal<input type="date" value={filtri.immatricolazione_da} onChange={imposta("immatricolazione_da")} /></label>
            <label>al<input type="date" value={filtri.immatricolazione_a} onChange={imposta("immatricolazione_a")} /></label>
            <label>Ultimo passaggio dal<input type="date" value={filtri.ultimo_passaggio_da} onChange={imposta("ultimo_passaggio_da")} /></label>
            <label>al<input type="date" value={filtri.ultimo_passaggio_a} onChange={imposta("ultimo_passaggio_a")} /></label>
            <label className="largo">
              Parole negli interventi (separate da virgola, ne basta una)
              <input value={filtri.parole} onChange={imposta("parole")} placeholder="TAGLIANDO, TGA, OLIO" />
            </label>
          </div>
          <div className="spunte">
            <label className="spunta"><input type="checkbox" checked={filtri.solo_con_telefono} onChange={spunta("solo_con_telefono")} />Solo clienti con un telefono</label>
            <label className="spunta"><input type="checkbox" checked={filtri.escludi_in_campagne_attive} onChange={spunta("escludi_in_campagne_attive")} />Salta i veicoli già in un'altra campagna attiva</label>
          </div>
          <p className="tenue">I clienti che hanno chiesto di non essere richiamati restano sempre fuori.</p>
          {anteprima && (
            <>
              <div className={anteprima.veicoli ? "messaggio-ok" : "errore"}>
                {anteprima.veicoli.toLocaleString("it-IT")} veicoli di {anteprima.clienti.toLocaleString("it-IT")} clienti con questi filtri.
              </div>
              {anteprima.esempi.length > 0 && (
                <table>
                  <thead><tr><th>Targa</th><th>Veicolo</th><th>Cliente</th><th>Immatricolazione</th><th>Ultimo passaggio</th></tr></thead>
                  <tbody>
                    {anteprima.esempi.map((v, i) => (
                      <tr key={i}>
                        <td className="targa">{v.targa}</td><td>{v.veicolo}</td><td>{v.cliente}</td>
                        <td>{formatoData(v.data_immatricolazione)}</td><td>{formatoData(v.data_ultimo_passaggio)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
          <div className="azioni">
            <button type="button" onClick={() => setAperto(false)}>Annulla</button>
            <button type="button" onClick={calcola}>Conta i veicoli</button>
            <button type="submit" className="primario" disabled={team.length === 0}>Crea campagna</button>
          </div>
        </form>
      )}
      <table>
        <thead>
          <tr>
            <th>Campagna</th><th>Motivo</th><th>Team</th><th>Creata il</th>
            <th className="num">Contatti</th><th className="num">Da chiamare</th><th className="num">Da richiamare</th><th className="num">Chiusi</th><th>Stato</th>
          </tr>
        </thead>
        <tbody>
          {campagne.map((c) => (
            <tr key={c.id} className={c.stato === "attiva" ? "" : "spento"}>
              <td><Link to={`/campagne/${c.id}`}>{c.nome}</Link></td>
              <td>{c.motivo}</td>
              <td>{c.team}</td>
              <td>{formatoData(c.creato_il)}</td>
              <td className="num">{c.totale}</td>
              <td className="num">{c.da_chiamare}</td>
              <td className="num">{c.richiamare}</td>
              <td className="num">{c.chiusi}</td>
              <td>{c.stato === "attiva" ? "Attiva" : "Chiusa"}</td>
            </tr>
          ))}
          {campagne.length === 0 && <tr><td colSpan={9} className="vuoto">Non ci sono ancora campagne</td></tr>}
        </tbody>
      </table>
    </>
  );
}
