import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, formatoData, post, query, type Campagna, type Voce } from "../api";
import Paginatore from "../components/Paginatore";

type Team = { id: number; nome: string; attivo: boolean; membri: unknown[] };
type Riga = {
  targa: string | null; veicolo: string; cliente: string; telefono: string | null;
  data_immatricolazione: string | null; data_ultimo_passaggio: string | null;
};
type Elenco = { veicoli: number; clienti: number; esempi: Riga[] };

const PER_PAGINA = 25;

const FILTRI_VUOTI = {
  q: "",
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
type Filtri = typeof FILTRI_VUOTI;

function perApi(f: Filtri) {
  return {
    q: f.q || null,
    marca: f.marca || null,
    sede_id: f.sede_id ? Number(f.sede_id) : null,
    immatricolazione_da: f.immatricolazione_da || null,
    immatricolazione_a: f.immatricolazione_a || null,
    ultimo_passaggio_da: f.ultimo_passaggio_da || null,
    ultimo_passaggio_a: f.ultimo_passaggio_a || null,
    parole: f.parole.split(",").map((p) => p.trim()).filter(Boolean),
    solo_con_telefono: f.solo_con_telefono,
    escludi_in_campagne_attive: f.escludi_in_campagne_attive,
  };
}

// Si parte sempre dall'elenco dei veicoli: prima si filtra, poi dall'elenco filtrato si crea la campagna.
export default function CampagnaNuova() {
  const naviga = useNavigate();
  const [parametri] = useSearchParams();
  // Arrivando dalla pagina Veicoli i filtri impostati lì sono già compilati.
  const iniziali: Filtri = {
    ...FILTRI_VUOTI,
    ...Object.fromEntries([...parametri.entries()].filter(([k]) => k in FILTRI_VUOTI && typeof FILTRI_VUOTI[k as keyof Filtri] === "string")),
  };
  const [filtri, setFiltri] = useState<Filtri>(iniziali);
  const [applicati, setApplicati] = useState<Filtri>(iniziali);
  const [pagina, setPagina] = useState(1);
  const [elenco, setElenco] = useState<Elenco | null>(null);
  const [team, setTeam] = useState<Team[]>([]);
  const [motivi, setMotivi] = useState<Voce[]>([]);
  const [marche, setMarche] = useState<string[]>([]);
  const [sedi, setSedi] = useState<{ id: number; nome: string }[]>([]);
  const [nuova, setNuova] = useState({ nome: "", motivo_id: "", team_id: "" });
  const [errore, setErrore] = useState("");
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    api<Team[]>("/team").then((t) => setTeam(t.filter((x) => x.attivo))).catch(() => undefined);
    api<Voce[]>("/elenchi/motivo_richiamo").then(setMotivi).catch(() => undefined);
    api<string[]>("/marche").then(setMarche).catch(() => undefined);
    api<{ id: number; nome: string }[]>("/sedi").then(setSedi).catch(() => undefined);
  }, []);

  useEffect(() => {
    setErrore("");
    post<Elenco>(`/campagne/anteprima${query({ pagina, per_pagina: PER_PAGINA })}`, perApi(applicati))
      .then(setElenco)
      .catch((e) => setErrore(e.message));
  }, [applicati, pagina]);

  const imposta = (k: keyof Filtri) => (e: { target: { value: string } }) => setFiltri({ ...filtri, [k]: e.target.value });
  const spunta = (k: keyof Filtri) => (e: { target: { checked: boolean } }) => setFiltri({ ...filtri, [k]: e.target.checked });
  const daApplicare = JSON.stringify(filtri) !== JSON.stringify(applicati);

  function filtra(e: FormEvent) {
    e.preventDefault();
    setPagina(1);
    setApplicati(filtri);
  }

  async function crea(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setInCorso(true);
    try {
      const creata = await post<Campagna>("/campagne", {
        nome: nuova.nome,
        motivo_id: nuova.motivo_id ? Number(nuova.motivo_id) : null,
        team_id: Number(nuova.team_id),
        filtri: perApi(applicati),
      });
      naviga(`/campagne/${creata.id}`);
    } catch (err) {
      setErrore((err as Error).message);
      setInCorso(false);
    }
  }

  return (
    <>
      <Link to="/campagne" className="indietro">‹ Campagne</Link>
      <h1>Nuova campagna</h1>
      <h2 className="passo">1. Filtra i veicoli da richiamare</h2>
      <form className="scheda" onSubmit={filtra}>
        <div className="filtri">
          <label>Cerca<input value={filtri.q} onChange={imposta("q")} placeholder="Targa, telaio, modello, cliente" /></label>
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
          <label className="spunta"><input type="checkbox" checked={filtri.escludi_in_campagne_attive} onChange={spunta("escludi_in_campagne_attive")} />Salta i veicoli già in un'altra campagna aperta</label>
        </div>
        <div className="azioni">
          <button type="button" onClick={() => { setFiltri(FILTRI_VUOTI); setApplicati(FILTRI_VUOTI); setPagina(1); }}>Azzera</button>
          <button type="submit" className="primario">Filtra</button>
        </div>
      </form>

      {errore && <div className="errore">{errore}</div>}
      {elenco && (
        <p>
          <strong>{elenco.veicoli.toLocaleString("it-IT")} {elenco.veicoli === 1 ? "veicolo" : "veicoli"}</strong> di {elenco.clienti.toLocaleString("it-IT")} {elenco.clienti === 1 ? "cliente" : "clienti"} con questi filtri.{" "}
          <span className="tenue">I clienti che hanno chiesto di non essere richiamati restano sempre fuori.</span>
        </p>
      )}
      <table>
        <thead>
          <tr><th>Targa</th><th>Veicolo</th><th>Cliente</th><th>Telefono</th><th>Immatricolazione</th><th>Ultimo passaggio</th></tr>
        </thead>
        <tbody>
          {elenco?.esempi.map((v, i) => (
            <tr key={i}>
              <td className="targa">{v.targa}</td><td>{v.veicolo}</td><td>{v.cliente}</td><td>{v.telefono}</td>
              <td>{formatoData(v.data_immatricolazione)}</td><td>{formatoData(v.data_ultimo_passaggio)}</td>
            </tr>
          ))}
          {elenco && elenco.veicoli === 0 && <tr><td colSpan={6} className="vuoto">Nessun veicolo con questi filtri</td></tr>}
        </tbody>
      </table>
      {elenco && <Paginatore pagina={pagina} perPagina={PER_PAGINA} totale={elenco.veicoli} onCambia={setPagina} />}

      <h2 className="passo">2. Crea la campagna con questi veicoli</h2>
      <form className="scheda" onSubmit={crea}>
        {team.length === 0 && (
          <div className="errore">Serve almeno un team: crealo nella pagina <Link to="/team">Team</Link>.</div>
        )}
        {daApplicare && <div className="errore">Hai cambiato i filtri senza premere «Filtra»: la campagna prenderebbe l'elenco che vedi ora.</div>}
        <div className="filtri">
          <label className="largo">Nome<input required value={nuova.nome} onChange={(e) => setNuova({ ...nuova, nome: e.target.value })} placeholder="Tagliandi marzo" /></label>
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
        <p className="tenue">Dopo la creazione nome, team ed elenco non si possono più cambiare.</p>
        <div className="azioni">
          <button type="submit" className="primario" disabled={inCorso || team.length === 0 || !elenco || elenco.veicoli === 0}>
            Crea campagna{elenco ? ` con ${elenco.veicoli.toLocaleString("it-IT")} ${elenco.veicoli === 1 ? "veicolo" : "veicoli"}` : ""}
          </button>
        </div>
      </form>
    </>
  );
}
