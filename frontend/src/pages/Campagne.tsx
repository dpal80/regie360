import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, formatoData, STATI_CAMPAGNA, type Campagna } from "../api";

export default function Campagne() {
  const [campagne, setCampagne] = useState<Campagna[]>([]);
  const [errore, setErrore] = useState("");

  useEffect(() => {
    api<Campagna[]>("/campagne").then(setCampagne).catch((e) => setErrore(e.message));
  }, []);

  return (
    <>
      <div className="testata">
        <h1>Campagne</h1>
        <Link to="/campagne/nuova" className="bottone primario">Nuova campagna</Link>
      </div>
      <p className="tenue">
        Una campagna nasce da un elenco di veicoli filtrato. Una volta creata non si modifica: si può mettere in pausa,
        chiudere, oppure eliminare se è stata creata per errore.
      </p>
      {errore && <div className="errore">{errore}</div>}
      <table>
        <thead>
          <tr>
            <th>Campagna</th><th>Motivo</th><th>Team</th><th>Creata il</th>
            <th className="num">Contatti</th><th className="num">Da chiamare</th><th className="num">Da richiamare</th><th className="num">Chiusi</th><th>Stato</th>
          </tr>
        </thead>
        <tbody>
          {campagne.map((c) => (
            <tr key={c.id} className={c.stato === "chiusa" ? "spento" : ""}>
              <td><Link to={`/campagne/${c.id}`}>{c.nome}</Link></td>
              <td>{c.motivo}</td>
              <td>{c.team}</td>
              <td>{formatoData(c.creato_il)}</td>
              <td className="num">{c.totale}</td>
              <td className="num">{c.da_chiamare}</td>
              <td className="num">{c.richiamare}</td>
              <td className="num">{c.chiusi}</td>
              <td>{STATI_CAMPAGNA[c.stato]}</td>
            </tr>
          ))}
          {campagne.length === 0 && <tr><td colSpan={9} className="vuoto">Non ci sono ancora campagne</td></tr>}
        </tbody>
      </table>
    </>
  );
}
