import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, query, type Pagina } from "../api";
import Paginatore from "../components/Paginatore";

type Cliente = {
  id: number;
  codice: string | null;
  nominativo: string;
  telefono_cellulare: string | null;
  telefono_fisso: string | null;
  email: string | null;
  num_veicoli: number;
};

export default function Clienti() {
  const [q, setQ] = useState("");
  const [cerca, setCerca] = useState("");
  const [pagina, setPagina] = useState(1);
  const [dati, setDati] = useState<Pagina<Cliente> | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setCerca(q);
      setPagina(1);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    api<Pagina<Cliente>>(`/clienti${query({ q: cerca, pagina })}`)
      .then(setDati)
      .catch((e) => setErrore(e.message));
  }, [cerca, pagina]);

  return (
    <>
      <h1>Clienti</h1>
      <input
        className="cerca"
        placeholder="Cerca per nome, codice, telefono, email o targa"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      {errore && <div className="errore">{errore}</div>}
      <table>
        <thead>
          <tr>
            <th>Codice</th>
            <th>Nominativo</th>
            <th>Cellulare</th>
            <th>Fisso</th>
            <th>Email</th>
            <th className="num">Veicoli</th>
          </tr>
        </thead>
        <tbody>
          {dati?.elementi.map((c) => (
            <tr key={c.id}>
              <td>{c.codice}</td>
              <td><Link to={`/clienti/${c.id}`}>{c.nominativo}</Link></td>
              <td>{c.telefono_cellulare}</td>
              <td>{c.telefono_fisso}</td>
              <td>{c.email}</td>
              <td className="num">{c.num_veicoli}</td>
            </tr>
          ))}
          {dati && dati.elementi.length === 0 && (
            <tr><td colSpan={6} className="vuoto">Nessun cliente trovato</td></tr>
          )}
        </tbody>
      </table>
      {dati && <Paginatore pagina={pagina} perPagina={dati.per_pagina} totale={dati.totale} onCambia={setPagina} />}
    </>
  );
}
