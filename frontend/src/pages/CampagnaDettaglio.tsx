import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatoDataOra, patch, query, STATI_CONTATTO, type Campagna, type ContattoRiga, type Pagina } from "../api";
import Paginatore from "../components/Paginatore";

type Dettaglio = Campagna & {
  operatori: { nome: string; da_chiamare: number; richiamare: number; chiuso: number }[];
  membri: { id: number; nome: string }[];
};

export default function CampagnaDettaglio() {
  const { id } = useParams();
  const [campagna, setCampagna] = useState<Dettaglio | null>(null);
  const [contatti, setContatti] = useState<Pagina<ContattoRiga> | null>(null);
  const [stato, setStato] = useState("");
  const [pagina, setPagina] = useState(1);
  const [errore, setErrore] = useState("");

  const carica = () => {
    api<Dettaglio>(`/campagne/${id}`).then(setCampagna).catch((e) => setErrore(e.message));
    api<Pagina<ContattoRiga>>(`/campagne/${id}/contatti${query({ stato, pagina })}`)
      .then(setContatti)
      .catch((e) => setErrore(e.message));
  };
  useEffect(carica, [id, stato, pagina]);

  async function azione(f: () => Promise<unknown>) {
    setErrore("");
    try {
      await f();
      carica();
    } catch (e) {
      setErrore((e as Error).message);
    }
  }

  if (!campagna) return errore ? <div className="errore">{errore}</div> : <p className="tenue">Caricamento…</p>;
  const attiva = campagna.stato === "attiva";

  return (
    <>
      <Link to="/campagne" className="indietro">‹ Campagne</Link>
      <div className="testata">
        <h1>{campagna.nome}</h1>
        <button onClick={() => azione(() => patch(`/campagne/${id}`, { stato: attiva ? "chiusa" : "attiva" }))}>
          {attiva ? "Chiudi campagna" : "Riapri campagna"}
        </button>
      </div>
      <p className="tenue">
        {campagna.motivo ? `${campagna.motivo} · ` : ""}Team {campagna.team} · {attiva ? "Attiva" : "Chiusa"}
      </p>
      {errore && <div className="errore">{errore}</div>}
      <div className="tessere">
        <div className="tessera"><span>{campagna.totale}</span>contatti</div>
        <div className="tessera"><span>{campagna.da_chiamare}</span>da chiamare</div>
        <div className="tessera arancio"><span>{campagna.richiamare}</span>da richiamare</div>
        <div className="tessera"><span>{campagna.chiusi}</span>chiusi</div>
        <div className="tessera"><span>{campagna.in_coda}</span>ancora in coda</div>
      </div>
      {campagna.operatori.length > 0 && (
        <>
          <h2>Per operatore</h2>
          <table>
            <thead><tr><th>Operatore</th><th className="num">Da chiamare</th><th className="num">Da richiamare</th><th className="num">Chiusi</th></tr></thead>
            <tbody>
              {campagna.operatori.map((o) => (
                <tr key={o.nome}><td>{o.nome}</td><td className="num">{o.da_chiamare}</td><td className="num">{o.richiamare}</td><td className="num">{o.chiuso}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h2>Contatti</h2>
      <div className="filtri">
        <label>
          Stato
          <select value={stato} onChange={(e) => { setStato(e.target.value); setPagina(1); }}>
            <option value="">Tutti</option>
            {Object.entries(STATI_CONTATTO).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      <table>
        <thead>
          <tr><th>Cliente</th><th>Telefono</th><th>Veicolo</th><th>Stato</th><th>Ultimo esito</th><th>Richiamo</th><th className="num">Tentativi</th><th>Operatore</th></tr>
        </thead>
        <tbody>
          {contatti?.elementi.map((c) => (
            <tr key={c.id} className={c.stato === "chiuso" ? "spento" : ""}>
              <td><Link to={`/contatti/${c.id}`}>{c.cliente}</Link></td>
              <td>{c.telefono}</td>
              <td><span className="targa">{c.targa}</span> {c.veicolo}</td>
              <td>{STATI_CONTATTO[c.stato]}</td>
              <td>{c.ultimo_esito}</td>
              <td>{formatoDataOra(c.data_richiamo)}</td>
              <td className="num">{c.tentativi}</td>
              <td>
                {c.stato === "chiuso" ? c.operatore : (
                  <select
                    value={c.operatore_id ?? ""}
                    onChange={(e) => azione(() => patch(`/contatti/${c.id}`, { operatore_id: e.target.value ? Number(e.target.value) : null }))}
                  >
                    <option value="">In coda</option>
                    {c.operatore_id !== null && !campagna.membri.some((m) => m.id === c.operatore_id) && (
                      <option value={c.operatore_id}>{c.operatore}</option>
                    )}
                    {campagna.membri.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
                  </select>
                )}
              </td>
            </tr>
          ))}
          {contatti && contatti.elementi.length === 0 && <tr><td colSpan={8} className="vuoto">Nessun contatto</td></tr>}
        </tbody>
      </table>
      {contatti && <Paginatore pagina={pagina} perPagina={contatti.per_pagina} totale={contatti.totale} onCambia={setPagina} />}
    </>
  );
}
