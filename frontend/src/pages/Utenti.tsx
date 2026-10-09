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
  deve_cambiare_password: boolean;
  admin_emergenza: boolean;
  bloccato_fino: string | null;
  ultimo_accesso: string | null;
};

type UtenteAD = { username: string; nome: string; email: string | null; reparto: string | null; gia_nel_crm: boolean };
type Sfoglia = { base_dn: string; utenti: UtenteAD[]; troppi: boolean };

const VUOTO = { username: "", nome: "", ruolo: "operatore", interno: "", origine: "ad", password: "" };

// Password provvisoria leggibile (senza caratteri che si confondono come 0/O o 1/l).
function generaPassword(): string {
  const alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const valori = crypto.getRandomValues(new Uint32Array(12));
  return Array.from(valori, (v) => alfabeto[v % alfabeto.length]).join("");
}

export default function Utenti() {
  const { utente: io } = useAuth();
  const [utenti, setUtenti] = useState<Utente[]>([]);
  const [nuovo, setNuovo] = useState(VUOTO);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  // Le credenziali di dominio per sfogliare restano solo in questa pagina: il CRM non le salva.
  const [sfoglia, setSfoglia] = useState({ aperto: false, username: "", password: "", q: "" });
  const [trovati, setTrovati] = useState<Sfoglia | null>(null);
  const [ruoli, setRuoli] = useState<Record<string, string>>({});
  const [cercando, setCercando] = useState(false);

  async function cercaInAD(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setCercando(true);
    try {
      setTrovati(await post<Sfoglia>("/impostazioni/ad/utenti", { username: sfoglia.username, password: sfoglia.password, q: sfoglia.q }));
    } catch (err) {
      setTrovati(null);
      setErrore((err as Error).message);
    } finally {
      setCercando(false);
    }
  }

  function aggiungiDaAD(u: UtenteAD) {
    azione(async () => {
      await post("/utenti", { username: u.username, nome: u.nome, ruolo: ruoli[u.username] ?? "operatore", origine: "ad" });
      setTrovati((t) => t && { ...t, utenti: t.utenti.map((x) => (x.username === u.username ? { ...x, gia_nel_crm: true } : x)) });
      setAvviso(`${u.nome} ora può entrare nel CRM con le credenziali di Windows.`);
    });
  }

  const carica = () => api<Utente[]>("/utenti").then(setUtenti).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
  }, []);

  async function azione(f: () => Promise<unknown>) {
    setErrore("");
    setAvviso("");
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
      const locale = nuovo.origine === "locale";
      await post("/utenti", { ...nuovo, interno: nuovo.interno || null, password: locale ? nuovo.password : null });
      setNuovo(VUOTO);
      if (locale) {
        setAvviso(`Utente ${nuovo.username} creato. Comunicagli la password provvisoria «${nuovo.password}»: la cambierà al primo accesso.`);
      }
    });
  }

  const bloccato = (u: Utente) => u.bloccato_fino && new Date(u.bloccato_fino) > new Date();

  return (
    <>
      <h1>Utenti</h1>
      <p className="tenue">
        Gli utenti di dominio entrano con le credenziali di Windows (Active Directory); gli utenti locali con una password
        del CRM, che scelgono al primo accesso. Qui decidi chi può usare il CRM e con quale ruolo.
      </p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}
      <form className="filtri scheda" onSubmit={aggiungi}>
        <label>
          Accesso
          <select
            value={nuovo.origine}
            onChange={(e) => setNuovo({ ...nuovo, origine: e.target.value, password: e.target.value === "locale" ? generaPassword() : "" })}
          >
            <option value="ad">Utente di dominio (Windows)</option>
            <option value="locale">Utente locale del CRM</option>
          </select>
        </label>
        <label>{nuovo.origine === "locale" ? "Nome utente" : "Nome utente di dominio"}<input required value={nuovo.username} onChange={(e) => setNuovo({ ...nuovo, username: e.target.value })} placeholder="mario.rossi" /></label>
        <label>Nome e cognome<input required value={nuovo.nome} onChange={(e) => setNuovo({ ...nuovo, nome: e.target.value })} /></label>
        <label>
          Ruolo
          <select value={nuovo.ruolo} onChange={(e) => setNuovo({ ...nuovo, ruolo: e.target.value })}>
            <option value="operatore">Operatore</option>
            <option value="responsabile">Responsabile</option>
          </select>
        </label>
        <label>Interno telefonico<input value={nuovo.interno} onChange={(e) => setNuovo({ ...nuovo, interno: e.target.value })} /></label>
        {nuovo.origine === "locale" && (
          <label>
            Password provvisoria
            <input required minLength={10} value={nuovo.password} onChange={(e) => setNuovo({ ...nuovo, password: e.target.value })} />
          </label>
        )}
        <div className="azioni"><button className="primario" type="submit">Aggiungi utente</button></div>
      </form>
      <section className="scheda">
        <div className="testata">
          <h3>Scegli dall'Active Directory</h3>
          <button onClick={() => setSfoglia({ ...sfoglia, aperto: !sfoglia.aperto })}>{sfoglia.aperto ? "Chiudi" : "Sfoglia utenti di dominio"}</button>
        </div>
        {sfoglia.aperto && (
          <>
            <p className="tenue">
              Per leggere l'elenco il CRM entra nel dominio con le tue credenziali di Windows, che non vengono salvate.
              Si vedono gli utenti attivi sotto la Base DN impostata nella pagina Active Directory.
            </p>
            <form className="filtri" onSubmit={cercaInAD}>
              <label>Il tuo utente di dominio<input required value={sfoglia.username} onChange={(e) => setSfoglia({ ...sfoglia, username: e.target.value })} autoComplete="off" /></label>
              <label>Password<input required type="password" value={sfoglia.password} onChange={(e) => setSfoglia({ ...sfoglia, password: e.target.value })} autoComplete="off" /></label>
              <label>Cerca (facoltativo)<input value={sfoglia.q} onChange={(e) => setSfoglia({ ...sfoglia, q: e.target.value })} placeholder="Nome, utente o e-mail" /></label>
              <div className="azioni"><button className="primario" type="submit" disabled={cercando}>{cercando ? "Cerco…" : "Mostra utenti"}</button></div>
            </form>
            {trovati && (
              <>
                <p className="tenue">
                  {trovati.utenti.length} utenti in {trovati.base_dn}
                  {trovati.troppi ? ": l'elenco è stato tagliato, restringi la ricerca o la Base DN." : "."}
                </p>
                <table>
                  <thead><tr><th>Nome</th><th>Utente</th><th>E-mail</th><th>Reparto</th><th>Ruolo</th><th></th></tr></thead>
                  <tbody>
                    {trovati.utenti.map((u) => (
                      <tr key={u.username} className={u.gia_nel_crm ? "spento" : ""}>
                        <td>{u.nome}</td>
                        <td>{u.username}</td>
                        <td>{u.email}</td>
                        <td>{u.reparto}</td>
                        <td>
                          {!u.gia_nel_crm && (
                            <select value={ruoli[u.username] ?? "operatore"} onChange={(e) => setRuoli({ ...ruoli, [u.username]: e.target.value })}>
                              <option value="operatore">Operatore</option>
                              <option value="responsabile">Responsabile</option>
                            </select>
                          )}
                        </td>
                        <td>
                          <div className="azioni-riga">
                            {u.gia_nel_crm ? "Già nel CRM" : <button onClick={() => aggiungiDaAD(u)}>Aggiungi</button>}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {trovati.utenti.length === 0 && <tr><td colSpan={6} className="vuoto">Nessun utente trovato</td></tr>}
                  </tbody>
                </table>
              </>
            )}
          </>
        )}
      </section>
      <table>
        <thead>
          <tr><th>Utente</th><th>Accesso</th><th>Nome</th><th>Ruolo</th><th>Interno</th><th>Ultimo accesso</th><th>Stato</th><th></th></tr>
        </thead>
        <tbody>
          {utenti.map((u) => {
            const ioStesso = u.id === io?.id;
            const locale = u.origine === "locale";
            const adminEmergenza = u.admin_emergenza;
            return (
              <tr key={u.id} className={u.attivo ? "" : "spento"}>
                <td>{u.username}</td>
                <td>{locale ? "Locale" : "Dominio"}</td>
                <td>{u.nome}</td>
                <td>
                  <select
                    value={u.ruolo}
                    disabled={ioStesso || adminEmergenza}
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
                <td>
                  {!u.attivo ? "Disattivato" : bloccato(u) ? "Bloccato" : u.deve_cambiare_password ? "Primo accesso" : "Attivo"}
                </td>
                <td>
                  <div className="azioni-riga">
                  {bloccato(u) && <button onClick={() => azione(() => post(`/utenti/${u.id}/sblocca`))}>Sblocca</button>}
                  {locale && !ioStesso && (
                    <button
                      onClick={() => {
                        const password = generaPassword();
                        azione(async () => {
                          await post(`/utenti/${u.id}/password`, { password });
                          setAvviso(`Nuova password provvisoria per ${u.username}: «${password}». La cambierà al prossimo accesso.`);
                        });
                      }}
                    >
                      Nuova password
                    </button>
                  )}
                  {!ioStesso && !adminEmergenza && (
                    <button onClick={() => azione(() => patch(`/utenti/${u.id}`, { attivo: !u.attivo }))}>
                      {u.attivo ? "Disattiva" : "Riattiva"}
                    </button>
                  )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
