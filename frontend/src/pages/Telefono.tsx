import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { cancella, eSuperadmin, post } from "../api";
import { useAuth } from "../auth";
import { useTelefono, type StatoTelefono } from "../telefono";

export default function Telefono() {
  const { utente } = useAuth();
  const superadmin = eSuperadmin(utente);
  const { stato } = useTelefono();
  const [credenziali, setCredenziali] = useState({ username: utente?.username ?? "", password: "" });
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [inCorso, setInCorso] = useState(false);

  async function esegui(f: () => Promise<void>) {
    setErrore("");
    setAvviso("");
    setInCorso(true);
    try {
      await f();
    } catch (e) {
      setErrore((e as Error).message);
    } finally {
      setInCorso(false);
    }
  }

  function collega(e: FormEvent) {
    e.preventDefault();
    esegui(async () => {
      await post<StatoTelefono>("/telefonia/collega", credenziali);
      // Phone Island legge i dati solo quando parte: la pagina si ricarica per avviarlo con quelli nuovi.
      window.location.reload();
    });
  }

  function scollega() {
    esegui(async () => {
      await cancella("/telefonia/collega");
      window.location.reload();
    });
  }

  return (
    <>
      <h1>Telefono</h1>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}

      <section className="scheda">
        <h3>Il mio telefono</h3>
        {!stato?.attivo ? (
          <p className="tenue">
            La telefonia non è ancora attiva{superadmin ? <>: imposta il collegamento in <Link to="/impostazioni/nethvoice">Impostazioni › NethVoice</Link>.</> : ": deve configurarla un super-admin."}
          </p>
        ) : stato.collegato ? (
          <>
            <p>
              Telefono collegato, interno <strong>{stato.interno}</strong>. Phone Island compare in alto nella pagina:
              al primo uso il browser chiede il permesso per il microfono.
            </p>
            <div className="azioni"><button disabled={inCorso} onClick={scollega}>Scollega il telefono</button></div>
          </>
        ) : (
          <form className="filtri" onSubmit={collega}>
            <p className="tenue largo">
              Inserisci le tue credenziali di NethVoice (le stesse di Windows, se entri con l'utente di dominio).
              Servono una volta sola per ottenere l'accesso al telefono e non vengono salvate.
            </p>
            <label>Utente NethVoice<input required value={credenziali.username} onChange={(e) => setCredenziali({ ...credenziali, username: e.target.value })} autoComplete="off" /></label>
            <label>Password<input required type="password" value={credenziali.password} onChange={(e) => setCredenziali({ ...credenziali, password: e.target.value })} autoComplete="off" /></label>
            <div className="azioni"><button className="primario" type="submit" disabled={inCorso}>Collega il telefono</button></div>
          </form>
        )}
      </section>

    </>
  );
}
