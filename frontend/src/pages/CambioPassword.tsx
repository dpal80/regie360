import { useState, type FormEvent } from "react";
import { post } from "../api";
import { useAuth } from "../auth";

const MINIMO = 10;

export default function CambioPassword({ obbligatorio = false }: { obbligatorio?: boolean }) {
  const { ricarica, logout } = useAuth();
  const [attuale, setAttuale] = useState("");
  const [nuova, setNuova] = useState("");
  const [conferma, setConferma] = useState("");
  const [errore, setErrore] = useState("");
  const [fatto, setFatto] = useState(false);

  async function salva(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setFatto(false);
    if (nuova.length < MINIMO) return setErrore(`La nuova password deve avere almeno ${MINIMO} caratteri`);
    if (nuova !== conferma) return setErrore("Le due password nuove non coincidono");
    try {
      await post("/auth/password", { attuale, nuova });
      setAttuale("");
      setNuova("");
      setConferma("");
      setFatto(true);
      await ricarica();
    } catch (err) {
      setErrore((err as Error).message);
    }
  }

  return (
    <form onSubmit={salva} className={`scheda password`}>
      {obbligatorio ? <h1>Scegli la tua password</h1> : <h3>Cambia password</h3>}
      {obbligatorio && (
        <p className="tenue">È il tuo primo accesso o la password è stata reimpostata: scegline una nuova per continuare.</p>
      )}
      <label>
        Password attuale
        <input type="password" value={attuale} onChange={(e) => setAttuale(e.target.value)} autoComplete="current-password" required autoFocus={obbligatorio} />
      </label>
      <label>
        Nuova password (almeno {MINIMO} caratteri)
        <input type="password" value={nuova} onChange={(e) => setNuova(e.target.value)} autoComplete="new-password" required />
      </label>
      <label>
        Ripeti la nuova password
        <input type="password" value={conferma} onChange={(e) => setConferma(e.target.value)} autoComplete="new-password" required />
      </label>
      {errore && <div className="errore">{errore}</div>}
      {fatto && <div className="messaggio-ok">Password cambiata.</div>}
      <div className="azioni">
        {obbligatorio && <button type="button" onClick={logout}>Esci</button>}
        <button type="submit" className="primario">Salva</button>
      </div>
    </form>
  );
}
