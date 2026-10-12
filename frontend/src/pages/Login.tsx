import { useEffect, useState, type FormEvent } from "react";
import { api, ErroreApi, post } from "../api";
import { useAuth } from "../auth";

// accesso: nome utente e password · codice: secondo passaggio · dimenticata: chiede il codice per e-mail ·
// reimposta: codice ricevuto e nuova password
type Passo = "accesso" | "codice" | "dimenticata" | "reimposta";

export default function Login() {
  const { login } = useAuth();
  const [passo, setPasso] = useState<Passo>("accesso");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [codice, setCodice] = useState("");
  const [nuova, setNuova] = useState("");
  const [resetPossibile, setResetPossibile] = useState(false);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [invio, setInvio] = useState(false);

  useEffect(() => {
    api<{ reset_password: boolean }>("/auth/opzioni").then((o) => setResetPossibile(o.reset_password)).catch(() => undefined);
  }, []);

  function vai(nuovoPasso: Passo) {
    setErrore("");
    setCodice("");
    setPasso(nuovoPasso);
  }

  async function invia(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setInvio(true);
    try {
      if (passo === "accesso" || passo === "codice") {
        await login(username, password, passo === "codice" ? codice : undefined);
      } else if (passo === "dimenticata") {
        await post("/auth/password-dimenticata", { username });
        setAvviso("Se questo utente ha un'e-mail nel CRM, gli abbiamo spedito un codice. Vale 15 minuti.");
        vai("reimposta");
      } else {
        await post("/auth/password-reimposta", { username, codice, nuova });
        setAvviso("Password cambiata: ora puoi entrare.");
        setPassword("");
        setNuova("");
        vai("accesso");
      }
    } catch (err) {
      const richiesto = err instanceof ErroreApi && (err.dettagli as { codice_richiesto?: boolean } | null)?.codice_richiesto;
      if (richiesto && passo === "accesso") {
        // La password è giusta: manca il codice dell'app di autenticazione.
        vai("codice");
      } else {
        setErrore((err as Error).message);
        if (passo === "accesso") setPassword("");
        setCodice("");
      }
    } finally {
      setInvio(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={invia} className="scheda">
        <h1>
          <img src="/logo.svg" alt="Regie360" className="logo-login" />
        </h1>
        {passo === "accesso" && (
          <>
            <p className="tenue">Il CRM di REGIE AUTO. Accedi con le credenziali di Windows o con quelle che ti ha dato il responsabile</p>
            <label>
              Nome utente
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
            </label>
            <label>
              Password
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
            </label>
          </>
        )}
        {passo === "codice" && (
          <>
            <p className="tenue">Verifica in due passaggi: apri la tua app di autenticazione e scrivi il codice di 6 cifre per Regie360.</p>
            <label>
              Codice
              <input value={codice} onChange={(e) => setCodice(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={7} autoFocus required />
            </label>
          </>
        )}
        {passo === "dimenticata" && (
          <>
            <p className="tenue">
              Scrivi il tuo nome utente: ti mandiamo per e-mail un codice per scegliere una nuova password. Vale solo
              per gli utenti locali del CRM: la password di Windows si cambia da Windows.
            </p>
            <label>
              Nome utente
              <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
            </label>
          </>
        )}
        {passo === "reimposta" && (
          <>
            <label>
              Codice ricevuto per e-mail
              <input value={codice} onChange={(e) => setCodice(e.target.value)} inputMode="numeric" autoComplete="one-time-code" autoFocus required />
            </label>
            <label>
              Nuova password (almeno 10 caratteri)
              <input type="password" value={nuova} onChange={(e) => setNuova(e.target.value)} autoComplete="new-password" minLength={10} required />
            </label>
          </>
        )}
        {avviso && passo !== "codice" && <div className="messaggio-ok">{avviso}</div>}
        {errore && <div className="errore">{errore}</div>}
        <button type="submit" className="primario" disabled={invio}>
          {invio ? "Un momento…" : passo === "accesso" ? "Accedi" : passo === "codice" ? "Verifica" : passo === "dimenticata" ? "Mandami il codice" : "Cambia password"}
        </button>
        {passo === "accesso" && resetPossibile && (
          <button type="button" className="link scuro" onClick={() => { setAvviso(""); vai("dimenticata"); }}>Password dimenticata?</button>
        )}
        {passo !== "accesso" && (
          <button type="button" className="link scuro" onClick={() => { setAvviso(""); vai("accesso"); }}>‹ Torna all'accesso</button>
        )}
      </form>
    </div>
  );
}
