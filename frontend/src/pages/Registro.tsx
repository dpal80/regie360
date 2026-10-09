import { useEffect, useState } from "react";
import { api, formatoDataOra } from "../api";

type Voce = {
  id: number;
  username: string | null;
  azione: string;
  oggetto: string | null;
  dettaglio: Record<string, unknown> | null;
  ip: string | null;
  quando: string;
};

const NOMI: Record<string, string> = {
  login: "Accesso",
  login_fallito: "Accesso fallito",
  login_ad_non_raggiungibile: "AD non raggiungibile",
  cambio_password: "Cambio password",
  utente_creato: "Utente aggiunto",
  utente_modificato: "Utente modificato",
  utente_sbloccato: "Utente sbloccato",
  import_caricato: "File caricato",
  import_confermato: "Import confermato",
  import_annullato: "Import annullato",
  cliente_letto: "Scheda cliente aperta",
};

export default function Registro() {
  const [voci, setVoci] = useState<Voce[]>([]);
  useEffect(() => {
    api<Voce[]>("/audit").then(setVoci).catch(() => undefined);
  }, []);
  return (
    <>
      <h1>Registro attività</h1>
      <p className="tenue">Le ultime 200 operazioni: chi ha fatto cosa e quando.</p>
      <table>
        <thead><tr><th>Quando</th><th>Utente</th><th>Azione</th><th>Oggetto</th><th>Dettagli</th><th>IP</th></tr></thead>
        <tbody>
          {voci.map((v) => (
            <tr key={v.id}>
              <td>{formatoDataOra(v.quando)}</td>
              <td>{v.username}</td>
              <td>{NOMI[v.azione] ?? v.azione}</td>
              <td>{v.oggetto}</td>
              <td className="esempi">{v.dettaglio ? Object.entries(v.dettaglio).map(([k, x]) => `${k}: ${x}`).join(", ") : ""}</td>
              <td>{v.ip}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
