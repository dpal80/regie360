import { useState, type FormEvent } from "react";
import { post, put, type Utente } from "../api";
import { useAuth } from "../auth";
import CambioPassword from "./CambioPassword";

type Avvio = { segreto: string; qr_svg: string };

function Email() {
  const { utente, ricarica } = useAuth();
  const locale = utente?.origine === "locale";
  const [email, setEmail] = useState(utente?.email ?? "");
  const [password, setPassword] = useState("");
  const [errore, setErrore] = useState("");
  const [fatto, setFatto] = useState(false);

  async function salva(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setFatto(false);
    try {
      await put<Utente>("/auth/email", { email, password: locale ? password : null });
      setPassword("");
      setFatto(true);
      await ricarica();
    } catch (err) {
      setErrore((err as Error).message);
    }
  }

  return (
    <form className="scheda password" onSubmit={salva}>
      <h3>E-mail</h3>
      <p className="tenue">
        {locale
          ? "A questo indirizzo arriva il codice per scegliere una nuova password, se la dimentichi."
          : "Il tuo indirizzo per le comunicazioni del CRM."}
      </p>
      <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nome@regieauto.it" /></label>
      {locale && (
        <label>La tua password, per conferma<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></label>
      )}
      {errore && <div className="errore">{errore}</div>}
      {fatto && <div className="messaggio-ok">E-mail salvata.</div>}
      <div className="azioni"><button type="submit" className="primario">Salva</button></div>
    </form>
  );
}

function DueFattori() {
  const { utente, ricarica } = useAuth();
  const [avvio, setAvvio] = useState<Avvio | null>(null);
  const [spegni, setSpegni] = useState(false);
  const [codice, setCodice] = useState("");
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");

  async function esegui(f: () => Promise<void>) {
    setErrore("");
    setAvviso("");
    try {
      await f();
    } catch (err) {
      setErrore((err as Error).message);
      setCodice("");
    }
  }

  const inizia = () => esegui(async () => setAvvio(await post<Avvio>("/auth/2fa/avvia")));

  function conferma(e: FormEvent) {
    e.preventDefault();
    esegui(async () => {
      await post(spegni ? "/auth/2fa/disattiva" : "/auth/2fa/conferma", { codice });
      setAvviso(spegni ? "Verifica in due passaggi disattivata." : "Verifica in due passaggi attiva: dal prossimo accesso ti verrà chiesto il codice.");
      setAvvio(null);
      setSpegni(false);
      setCodice("");
      await ricarica();
    });
  }

  const campoCodice = (
    <label>
      Codice di 6 cifre
      <input className="corto" value={codice} onChange={(e) => setCodice(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={7} required autoFocus />
    </label>
  );

  return (
    <section className="scheda password">
      <h3>Verifica in due passaggi</h3>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}
      {utente?.totp_attivo ? (
        <>
          <p><strong>Attiva.</strong> Oltre alla password, a ogni accesso serve il codice della tua app di autenticazione.</p>
          {spegni ? (
            <form onSubmit={conferma}>
              {campoCodice}
              <div className="azioni">
                <button type="button" onClick={() => { setSpegni(false); setCodice(""); }}>Annulla</button>
                <button type="submit">Disattiva</button>
              </div>
            </form>
          ) : (
            <div className="azioni"><button onClick={() => setSpegni(true)}>Disattiva…</button></div>
          )}
          <p className="tenue">Se perdi il telefono, un super-admin può azzerarla dalla pagina Utenti.</p>
        </>
      ) : avvio ? (
        <form onSubmit={conferma}>
          <p>
            1. Apri un'app di autenticazione (Microsoft Authenticator, Google Authenticator o simili) e inquadra questo codice.
          </p>
          <div className="qr" dangerouslySetInnerHTML={{ __html: avvio.qr_svg }} />
          <p className="tenue">Se non puoi inquadrarlo, scrivi nell'app questa chiave: <code>{avvio.segreto}</code></p>
          <p>2. Scrivi qui il codice che l'app ti mostra.</p>
          {campoCodice}
          <div className="azioni">
            <button type="button" onClick={() => { setAvvio(null); setCodice(""); }}>Annulla</button>
            <button type="submit" className="primario">Attiva</button>
          </div>
        </form>
      ) : (
        <>
          <p>
            <strong>Consigliata, non obbligatoria.</strong> Con la verifica in due passaggi, per entrare serve anche un
            codice generato dal tuo telefono: chi scopre la tua password non può usarla da solo.
          </p>
          <div className="azioni"><button className="primario" onClick={inizia}>Attiva la verifica in due passaggi</button></div>
        </>
      )}
    </section>
  );
}

export default function Account() {
  const { utente } = useAuth();
  return (
    <>
      <h1>Il mio account</h1>
      <DueFattori />
      <Email />
      {utente?.origine === "locale" && <CambioPassword />}
    </>
  );
}
