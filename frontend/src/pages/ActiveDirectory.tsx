import { useEffect, useState, type FormEvent } from "react";
import { api, cancella, post, put } from "../api";

type Config = { server: string; porta: number; ssl: boolean; dominio: string; certificato_ca: string; base_dn: string; origine: string };
type Prova = { ok: boolean; messaggio: string };

const VUOTA: Config = { server: "", porta: 636, ssl: true, dominio: "", certificato_ca: "", base_dn: "", origine: "nessuna" };

const ORIGINI: Record<string, string> = {
  pagina: "Impostazioni salvate da questa pagina.",
  file: "Impostazioni lette dal file di configurazione del server: salvandole qui, varranno quelle di questa pagina.",
  nessuna: "Active Directory non ancora configurato: per ora entrano solo gli utenti locali.",
};

export default function ActiveDirectory() {
  const [config, setConfig] = useState<Config>(VUOTA);
  const [utenteProva, setUtenteProva] = useState({ username: "", password: "" });
  const [prova, setProva] = useState<Prova | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");

  useEffect(() => {
    api<Config>("/impostazioni/ad").then(setConfig).catch((e) => setErrore(e.message));
  }, []);

  const dati = () => ({
    server: config.server, porta: Number(config.porta), ssl: config.ssl,
    dominio: config.dominio, certificato_ca: config.certificato_ca, base_dn: config.base_dn,
  });

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

  function salva(e: FormEvent) {
    e.preventDefault();
    esegui(async () => {
      setConfig(await put<Config>("/impostazioni/ad", dati()));
      setAvviso("Impostazioni salvate: valgono da subito per i prossimi accessi.");
    });
  }

  function provaCollegamento() {
    setProva(null);
    esegui(async () => {
      setProva(await post<Prova>("/impostazioni/ad/prova", { ...dati(), ...utenteProva }));
      setUtenteProva({ ...utenteProva, password: "" });
    });
  }

  function rimuovi() {
    if (!confirm("Togliere le impostazioni salvate da questa pagina? Gli utenti di dominio non potranno più entrare.")) return;
    esegui(async () => {
      setConfig(await cancella<Config>("/impostazioni/ad"));
      setAvviso("Impostazioni rimosse.");
    });
  }

  const completo = config.server.trim() !== "" && config.dominio.trim() !== "";

  return (
    <>
      <h1>Active Directory</h1>
      <p className="tenue">
        Qui colleghi il CRM al dominio Windows della sede. Il CRM chiede al server di dominio solo di verificare la
        password: chi può entrare e con quale ruolo lo decidi tu nella pagina Utenti.
      </p>
      <p className="tenue">{ORIGINI[config.origine]}</p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}
      <form className="scheda modulo" onSubmit={salva}>
        <label>
          Server di dominio
          <input required value={config.server} onChange={(e) => setConfig({ ...config, server: e.target.value })} placeholder="dc1.regieauto.local" />
        </label>
        <label>
          Dominio
          <input required value={config.dominio} onChange={(e) => setConfig({ ...config, dominio: e.target.value })} placeholder="regieauto.local" />
        </label>
        <label>
          Porta
          <input className="corto" type="number" min={1} max={65535} required value={config.porta} onChange={(e) => setConfig({ ...config, porta: Number(e.target.value) })} />
        </label>
        <label className="spunta">
          <input
            type="checkbox"
            checked={config.ssl}
            onChange={(e) => setConfig({ ...config, ssl: e.target.checked, porta: e.target.checked ? 636 : 389 })}
          />
          Collegamento cifrato (LDAPS)
        </label>
        {!config.ssl && (
          <div className="errore larga">Senza collegamento cifrato le password viaggiano in chiaro sulla rete: usalo solo per una prova.</div>
        )}
        <label className="larga">
          Base DN: da dove sfogliare gli utenti nella pagina Utenti (vuota = tutto il dominio)
          <input value={config.base_dn} onChange={(e) => setConfig({ ...config, base_dn: e.target.value })} placeholder="OU=Operatori CRM,DC=regieauto,DC=local" />
        </label>
        <label className="larga">
          Certificato della CA interna (formato PEM, facoltativo)
          <textarea
            rows={6}
            value={config.certificato_ca}
            onChange={(e) => setConfig({ ...config, certificato_ca: e.target.value })}
            placeholder={"-----BEGIN CERTIFICATE-----\n…\n-----END CERTIFICATE-----"}
          />
        </label>

        <h2 className="larga">Prova il collegamento</h2>
        <p className="tenue larga">
          Inserisci un utente di dominio qualsiasi: il CRM prova ad accedere con i dati qui sopra, anche prima di
          salvarli. La password non viene salvata.
        </p>
        <label>
          Nome utente di dominio
          <input value={utenteProva.username} onChange={(e) => setUtenteProva({ ...utenteProva, username: e.target.value })} placeholder="mario.rossi" autoComplete="off" />
        </label>
        <label>
          Password
          <input type="password" value={utenteProva.password} onChange={(e) => setUtenteProva({ ...utenteProva, password: e.target.value })} autoComplete="off" />
        </label>
        <div className="azioni larga">
          <button type="button" disabled={inCorso || !completo || !utenteProva.username || !utenteProva.password} onClick={provaCollegamento}>
            Prova collegamento
          </button>
        </div>
        {prova && <div className={`${prova.ok ? "messaggio-ok" : "errore"} larga`}>{prova.messaggio}</div>}

        <div className="azioni larga">
          {config.origine === "pagina" && <button type="button" disabled={inCorso} onClick={rimuovi}>Rimuovi impostazioni</button>}
          <button type="submit" className="primario" disabled={inCorso}>Salva</button>
        </div>
      </form>
    </>
  );
}
