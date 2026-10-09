import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, formatoDataOra, post, STATI_CONTATTO, type Campagna, type ContattoRiga } from "../api";

export default function Chiamate() {
  const naviga = useNavigate();
  const [campagne, setCampagne] = useState<Campagna[] | null>(null);
  const [contatti, setContatti] = useState<ContattoRiga[]>([]);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    api<Campagna[]>("/campagne").then((c) => setCampagne(c.filter((x) => x.stato === "attiva"))).catch((e) => setErrore(e.message));
    api<ContattoRiga[]>("/contatti/miei").then(setContatti).catch((e) => setErrore(e.message));
  }, []);

  async function prossimo(campagnaId: number) {
    setErrore("");
    try {
      const r = await post<{ contatto_id: number }>(`/campagne/${campagnaId}/prossimo`);
      naviga(`/contatti/${r.contatto_id}`);
    } catch (e) {
      setErrore((e as Error).message);
    }
  }

  const scaduto = (c: ContattoRiga) => c.data_richiamo !== null && new Date(c.data_richiamo) <= new Date();

  return (
    <>
      <h1>Le mie chiamate</h1>
      {errore && <div className="errore">{errore}</div>}
      <h2>Campagne</h2>
      {campagne?.length === 0 && <p className="tenue">Nessuna campagna attiva per i tuoi team.</p>}
      <div className="tessere">
        {campagne?.map((c) => (
          <div key={c.id} className="scheda campagna">
            <h3>{c.nome}</h3>
            <p className="tenue">{c.motivo ? `${c.motivo} · ` : ""}Team {c.team}</p>
            <p>{c.in_coda} in coda · {c.miei} miei aperti</p>
            <button className="primario" disabled={c.in_coda + c.miei === 0} onClick={() => prossimo(c.id)}>
              Prossimo contatto
            </button>
          </div>
        ))}
      </div>
      <h2>I miei contatti aperti</h2>
      <table>
        <thead>
          <tr><th>Cliente</th><th>Telefono</th><th>Veicolo</th><th>Campagna</th><th>Stato</th><th>Ultimo esito</th><th>Richiamo</th></tr>
        </thead>
        <tbody>
          {contatti.map((c) => (
            <tr key={c.id}>
              <td><Link to={`/contatti/${c.id}`}>{c.cliente}</Link></td>
              <td>{c.telefono}</td>
              <td><span className="targa">{c.targa}</span> {c.veicolo}</td>
              <td>{c.campagna}</td>
              <td>{STATI_CONTATTO[c.stato]}</td>
              <td>{c.ultimo_esito}</td>
              <td className={scaduto(c) ? "scaduto" : ""}>{formatoDataOra(c.data_richiamo)}</td>
            </tr>
          ))}
          {contatti.length === 0 && (
            <tr><td colSpan={7} className="vuoto">Nessun contatto aperto: prendine uno con «Prossimo contatto»</td></tr>
          )}
        </tbody>
      </table>
    </>
  );
}
