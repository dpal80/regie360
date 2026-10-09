import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";

export default function Login() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errore, setErrore] = useState("");
  const [invio, setInvio] = useState(false);

  async function entra(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setInvio(true);
    try {
      await login(username, password);
    } catch (err) {
      setErrore((err as Error).message);
      setPassword("");
    } finally {
      setInvio(false);
    }
  }

  return (
    <div className="login">
      <form onSubmit={entra} className="scheda">
        <h1>
          CRM <strong>REGIE AUTO</strong>
        </h1>
        <p className="tenue">Accedi con le credenziali di Windows</p>
        <label>
          Nome utente
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {errore && <div className="errore">{errore}</div>}
        <button type="submit" className="primario" disabled={invio}>
          {invio ? "Accesso in corso…" : "Accedi"}
        </button>
      </form>
    </div>
  );
}
