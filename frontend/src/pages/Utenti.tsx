import { useEffect, useState, type FormEvent } from "react";
import { api, formatoDataOra, patch, post } from "../api";
import { useAuth } from "../auth";

type Utente = {
  id: number;
  username: string;
  nome: string;
  ruolo: "responsabile" | "operatore";
  origine: "ad" | "locale";
  interno: string | null;
  attivo: boolean;
  bloccato_fino: string | null;
  ultimo_accesso: string | null;
};

const VUOTO = { username: "", nome: "", ruolo: "operatore", interno: "" };

export default function Utenti() {
  const { utente: io } = useAuth();
  const [utenti, setUtenti] = useState<Utente[]>([]);
  const [nuovo, setNuovo] = useState(VUOTO);
  const [errore, setErrore] = useState("");

  const carica = () => api<Utente[]>("/utenti").then(setUtenti).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
  }, []);

  async function azione(f: () => Promise<unknown>) {
    setErrore("");
    try {
      await f();
      await carica();
    } catch (e) {
      setErrore((e as Error).message);
    }
  }

  function aggiungi(e: FormEvent) {
    e.preventDefault();
    azione(async () => {
      await post("/utenti", { ...nuovo, interno: nuovo.interno || null });
      setNuovo(VUOTO);
    });
  }

  const bloccato = (u: Utente) => u.bloccato_fino && new Date(u.bloccato_fino) > new Date();

  return (
    <>
      <h1>Utenti</h1>
      <p className="tenue">
        Gli utenti entrano con le credenziali di Windows (Active Directory). Qui decidi chi può usare il CRM e con quale ruolo.
      </p>
      {errore && <div className="errore">{errore}</div>}
      <form className="filtri scheda" onSubmit={aggiungi}>
        <label>Nome utente di dominio<input required value={nuovo.username} onChange={(e) => setNuovo({ ...nuovo, username: e.target.value })} placeholder="mario.rossi" /></label>
        <label>Nome e cognome<input required value={nuovo.nome} onChange={(e) => setNuovo({ ...nuovo, nome: e.target.value })} /></label>
        <label>
          Ruolo
          <select value={nuovo.ruolo} onChange={(e) => setNuovo({ ...nuovo, ruolo: e.target.value })}>
            <option value="operatore">Operatore</option>
            <option value="responsabile">Responsabile</option>
          </select>
        </label>
        <label>Interno telefonico<input value={nuovo.interno} onChange={(e) => setNuovo({ ...nuovo, interno: e.target.value })} /></label>
        <div className="azioni"><button className="primario" type="submit">Aggiungi utente</button></div>
      </form>
      <table>
        <thead>
          <tr><th>Utente</th><th>Nome</th><th>Ruolo</th><th>Interno</th><th>Ultimo accesso</th><th>Stato</th><th></th></tr>
        </thead>
        <tbody>
          {utenti.map((u) => {
            const ioStesso = u.id === io?.id;
            const locale = u.origine === "locale";
            return (
              <tr key={u.id} className={u.attivo ? "" : "spento"}>
                <td>{u.username}{locale && <small className="tenue"> (locale)</small>}</td>
                <td>{u.nome}</td>
                <td>
                  <select
                    value={u.ruolo}
                    disabled={ioStesso || locale}
                    onChange={(e) => azione(() => patch(`/utenti/${u.id}`, { ruolo: e.target.value }))}
                  >
                    <option value="operatore">Operatore</option>
                    <option value="responsabile">Responsabile</option>
                  </select>
                </td>
                <td>
                  <input
                    className="corto"
                    defaultValue={u.interno ?? ""}
                    onBlur={(e) => e.target.value !== (u.interno ?? "") && azione(() => patch(`/utenti/${u.id}`, { interno: e.target.value }))}
                  />
                </td>
                <td>{formatoDataOra(u.ultimo_accesso)}</td>
                <td>{!u.attivo ? "Disattivato" : bloccato(u) ? "Bloccato" : "Attivo"}</td>
                <td className="azioni-riga">
                  {bloccato(u) && <button onClick={() => azione(() => post(`/utenti/${u.id}/sblocca`))}>Sblocca</button>}
                  {!ioStesso && !locale && (
                    <button onClick={() => azione(() => patch(`/utenti/${u.id}`, { attivo: !u.attivo }))}>
                      {u.attivo ? "Disattiva" : "Riattiva"}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
