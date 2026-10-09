import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, formatoData } from "../api";

type Passaggio = {
  id: number;
  numero_or: string | null;
  sede: string | null;
  descrizione: string | null;
  data_apertura: string | null;
  data_chiusura: string | null;
};

type Veicolo = {
  id: number;
  targa: string | null;
  telaio: string | null;
  marca: string | null;
  modello: string | null;
  data_immatricolazione: string | null;
  data_ultimo_passaggio: string | null;
  extra: Record<string, unknown>;
  passaggi: Passaggio[];
};

type Cliente = {
  id: number;
  codice: string | null;
  nominativo: string;
  tipo: string | null;
  telefono_cellulare: string | null;
  telefono_fisso: string | null;
  email: string | null;
  veicoli: Veicolo[];
};

export default function ClienteDettaglio() {
  const { id } = useParams();
  const [c, setC] = useState<Cliente | null>(null);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    api<Cliente>(`/clienti/${id}`).then(setC).catch((e) => setErrore(e.message));
  }, [id]);

  if (errore) return <div className="errore">{errore}</div>;
  if (!c) return <div>Caricamento…</div>;

  return (
    <>
      <Link to="/clienti" className="indietro">‹ Clienti</Link>
      <h1>{c.nominativo}</h1>
      <dl className="dati">
        <dt>Codice cliente</dt><dd>{c.codice ?? "—"}</dd>
        <dt>Cellulare</dt><dd>{c.telefono_cellulare ?? "—"}</dd>
        <dt>Fisso</dt><dd>{c.telefono_fisso ?? "—"}</dd>
        <dt>Email</dt><dd>{c.email ?? "—"}</dd>
        {c.tipo && (<><dt>Tipo</dt><dd>{c.tipo}</dd></>)}
      </dl>

      <h2>Veicoli ({c.veicoli.length})</h2>
      {c.veicoli.map((v) => (
        <section key={v.id} className="scheda veicolo">
          <h3>
            {v.marca} {v.modello} <span className="targa">{v.targa}</span>
          </h3>
          <div className="tenue">
            Telaio {v.telaio ?? "—"} · Immatricolata il {formatoData(v.data_immatricolazione) || "—"} · Ultimo passaggio{" "}
            {formatoData(v.data_ultimo_passaggio) || "—"}
          </div>
          {Object.keys(v.extra).length > 0 && (
            <div className="extra">
              {Object.entries(v.extra).map(([k, val]) => (
                <span key={k}>{k}: <strong>{String(val)}</strong></span>
              ))}
            </div>
          )}
          {v.passaggi.length > 0 && (
            <table>
              <thead>
                <tr><th>O.R.</th><th>Apertura</th><th>Chiusura</th><th>Sede</th><th>Intervento</th></tr>
              </thead>
              <tbody>
                {v.passaggi.map((p) => (
                  <tr key={p.id}>
                    <td>{p.numero_or}</td>
                    <td>{formatoData(p.data_apertura)}</td>
                    <td>{formatoData(p.data_chiusura)}</td>
                    <td>{p.sede}</td>
                    <td>{p.descrizione}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ))}
    </>
  );
}
