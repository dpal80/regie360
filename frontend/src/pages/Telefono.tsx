import { useEffect, useState, type FormEvent } from "react";
import { api, cancella, post, put } from "../api";
import { useAuth } from "../auth";
import { useTelefono, type StatoTelefono } from "../telefono";

type NethVoice = { attivo: boolean; cti_host: string; sip_host: string; sip_porta: string; certificato_ca: string };

const VUOTA: NethVoice = { attivo: true, cti_host: "", sip_host: "", sip_porta: "", certificato_ca: "" };

export default function Telefono() {
  const { utente } = useAuth();
  const superadmin = utente?.ruolo === "superadmin";
  const { stato, ricarica } = useTelefono();
  const [credenziali, setCredenziali] = useState({ username: utente?.username ?? "", password: "" });
  const [config, setConfig] = useState<NethVoice>(VUOTA);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    if (!superadmin) return;
    api<NethVoice>("/impostazioni/nethvoice")
      // Finché non è mai stata configurata, la spunta "attiva" parte accesa.
      .then((c) => setConfig(c.cti_host ? c : { ...c, attivo: true }))
      .catch((e) => setErrore(e.message));
  }, [superadmin]);

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

  function salva(e: FormEvent) {
    e.preventDefault();
    esegui(async () => {
      setConfig(await put<NethVoice>("/impostazioni/nethvoice", config));
      await ricarica();
      setAvviso("Impostazioni salvate. Ogni operatore collega il suo telefono da questa stessa pagina.");
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
            La telefonia non è ancora attiva{superadmin ? ": compila qui sotto il collegamento a NethVoice." : ": deve configurarla un super-admin."}
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

      {superadmin && (
        <form className="scheda modulo" onSubmit={salva}>
          <h3 className="larga">Collegamento a NethVoice</h3>
          <label>
            Server CTI di NethVoice
            <input required value={config.cti_host} onChange={(e) => setConfig({ ...config, cti_host: e.target.value })} placeholder="cti.regieauto.local" />
          </label>
          <label>
            Server SIP (telefono web)
            <input required value={config.sip_host} onChange={(e) => setConfig({ ...config, sip_host: e.target.value })} placeholder="voice.regieauto.local" />
          </label>
          <label>
            Porta SIP
            <input className="corto" required inputMode="numeric" pattern="\d+" value={config.sip_porta} onChange={(e) => setConfig({ ...config, sip_porta: e.target.value })} />
          </label>
          <label className="spunta">
            <input type="checkbox" checked={config.attivo} onChange={(e) => setConfig({ ...config, attivo: e.target.checked })} />
            Telefonia attiva
          </label>
          <label className="larga">
            Certificato della CA interna (formato PEM, facoltativo)
            <textarea rows={5} value={config.certificato_ca} onChange={(e) => setConfig({ ...config, certificato_ca: e.target.value })} placeholder={"-----BEGIN CERTIFICATE-----\n…\n-----END CERTIFICATE-----"} />
          </label>
          <p className="tenue larga">
            Server e porta SIP sono quelli che usa la CTI web di NethVoice: li trovi nella configurazione del
            centralino. Anche i PC degli operatori devono raggiungere questi indirizzi.
          </p>
          <div className="azioni larga"><button type="submit" className="primario" disabled={inCorso}>Salva</button></div>
        </form>
      )}
    </>
  );
}
