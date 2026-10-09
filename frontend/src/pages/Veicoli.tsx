import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatoData, query, type Pagina } from "../api";
import Paginatore from "../components/Paginatore";

type Veicolo = {
  id: number;
  targa: string | null;
  marca: string | null;
  modello: string | null;
  data_immatricolazione: string | null;
  data_ultimo_passaggio: string | null;
  cliente_id: number | null;
  cliente_nominativo: string | null;
  cliente_telefono: string | null;
};

const FILTRI_VUOTI = {
  q: "",
  marca: "",
  sede_id: "",
  immatricolazione_da: "",
  immatricolazione_a: "",
  ultimo_passaggio_da: "",
  ultimo_passaggio_a: "",
};

export default function Veicoli() {
  const [filtri, setFiltri] = useState(FILTRI_VUOTI);
  const [applicati, setApplicati] = useState(FILTRI_VUOTI);
  const [pagina, setPagina] = useState(1);
  const [dati, setDati] = useState<Pagina<Veicolo> | null>(null);
  const [marche, setMarche] = useState<string[]>([]);
  const [sedi, setSedi] = useState<{ id: number; nome: string }[]>([]);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    api<string[]>("/marche").then(setMarche).catch(() => undefined);
    api<{ id: number; nome: string }[]>("/sedi").then(setSedi).catch(() => undefined);
  }, []);

  useEffect(() => {
    setErrore("");
    api<Pagina<Veicolo>>(`/veicoli${query({ ...applicati, pagina })}`)
      .then(setDati)
      .catch((e) => setErrore(e.message));
  }, [applicati, pagina]);

  const imposta = (k: keyof typeof filtri) => (e: { target: { value: string } }) =>
    setFiltri({ ...filtri, [k]: e.target.value });

  return (
    <>
      <h1>Veicoli</h1>
      <form
        className="filtri"
        onSubmit={(e) => {
          e.preventDefault();
          setPagina(1);
          setApplicati(filtri);
        }}
      >
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
        <div className="azioni">
          <button type="submit" className="primario">Filtra</button>
          <button type="button" onClick={() => { setFiltri(FILTRI_VUOTI); setApplicati(FILTRI_VUOTI); setPagina(1); }}>
            Azzera
          </button>
        </div>
      </form>
      {errore && <div className="errore">{errore}</div>}
      <table>
        <thead>
          <tr>
            <th>Targa</th>
            <th>Marca e modello</th>
            <th>Immatricolazione</th>
            <th>Ultimo passaggio</th>
            <th>Cliente</th>
            <th>Telefono</th>
          </tr>
        </thead>
        <tbody>
          {dati?.elementi.map((v) => (
            <tr key={v.id}>
              <td className="targa">{v.targa}</td>
              <td>{v.marca} {v.modello}</td>
              <td>{formatoData(v.data_immatricolazione)}</td>
              <td>{formatoData(v.data_ultimo_passaggio)}</td>
              <td>{v.cliente_id && <Link to={`/clienti/${v.cliente_id}`}>{v.cliente_nominativo}</Link>}</td>
              <td>{v.cliente_telefono}</td>
            </tr>
          ))}
          {dati && dati.elementi.length === 0 && (
            <tr><td colSpan={6} className="vuoto">Nessun veicolo con questi filtri</td></tr>
          )}
        </tbody>
      </table>
      {dati && <Paginatore pagina={pagina} perPagina={dati.per_pagina} totale={dati.totale} onCambia={setPagina} />}
    </>
  );
}
