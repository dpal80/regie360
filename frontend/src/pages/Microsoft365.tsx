import { useEffect, useState, type FormEvent } from "react";
import { api, post, put } from "../api";

type Config = { attivo: boolean; tenant_id: string; client_id: string; mittente: string; segreto_presente: boolean };
type Prova = { ok: boolean; messaggio: string };

const VUOTA: Config = { attivo: true, tenant_id: "", client_id: "", mittente: "", segreto_presente: false };

export default function Microsoft365() {
  const [config, setConfig] = useState<Config>(VUOTA);
  const [segreto, setSegreto] = useState("");
  const [destinatario, setDestinatario] = useState("");
  const [prova, setProva] = useState<Prova | null>(null);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    api<Config>("/impostazioni/microsoft365")
      .then((c) => setConfig(c.tenant_id ? c : { ...c, attivo: true }))
      .catch((e) => setErrore(e.message));
  }, []);

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
      setConfig(await put<Config>("/impostazioni/microsoft365", {
        attivo: config.attivo, tenant_id: config.tenant_id, client_id: config.client_id, mittente: config.mittente, segreto,
      }));
      setSegreto("");
      setAvviso("Impostazioni salvate.");
    });
  }

  function inviaProva(e: FormEvent) {
    e.preventDefault();
    setProva(null);
    esegui(async () => setProva(await post<Prova>("/impostazioni/microsoft365/prova", { destinatario })));
  }

  return (
    <>
      <p className="tenue">
        Il CRM spedisce le e-mail attraverso un'app registrata nel vostro Microsoft 365 (Entra ID), dalla casella che
        scegli come mittente. All'app serve il permesso applicativo <strong>Mail.Send</strong> con il consenso
        dell'amministratore.
      </p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}
      <form className="scheda modulo" onSubmit={salva}>
        <label>
          ID tenant (directory)
          <input required value={config.tenant_id} onChange={(e) => setConfig({ ...config, tenant_id: e.target.value })} placeholder="00000000-0000-0000-0000-000000000000" />
        </label>
        <label>
          ID applicazione (client)
          <input required value={config.client_id} onChange={(e) => setConfig({ ...config, client_id: e.target.value })} placeholder="00000000-0000-0000-0000-000000000000" />
        </label>
        <label>
          Segreto dell'applicazione
          <input
            type="password"
            autoComplete="off"
            required={!config.segreto_presente}
            value={segreto}
            onChange={(e) => setSegreto(e.target.value)}
            placeholder={config.segreto_presente ? "Già salvato: scrivi solo per cambiarlo" : ""}
          />
        </label>
        <label>
          Casella mittente
          <input required type="email" value={config.mittente} onChange={(e) => setConfig({ ...config, mittente: e.target.value })} placeholder="crm@regieauto.it" />
        </label>
        <label className="spunta larga">
          <input type="checkbox" checked={config.attivo} onChange={(e) => setConfig({ ...config, attivo: e.target.checked })} />
          Invio e-mail attivo
        </label>
        <p className="tenue larga">Il segreto viene salvato cifrato e non viene più mostrato. Ricorda che in Entra ID ha una scadenza.</p>
        <div className="azioni larga"><button type="submit" className="primario" disabled={inCorso}>Salva</button></div>
      </form>

      <form className="scheda" onSubmit={inviaProva}>
        <h3>E-mail di prova</h3>
        <div className="filtri">
          <label className="largo">
            Spedisci a
            <input required type="email" value={destinatario} onChange={(e) => setDestinatario(e.target.value)} placeholder="tuo.nome@regieauto.it" />
          </label>
          <div className="azioni"><button type="submit" disabled={inCorso || !config.segreto_presente}>Invia prova</button></div>
        </div>
        {prova && <div className={prova.ok ? "messaggio-ok" : "errore"}>{prova.messaggio}</div>}
      </form>
    </>
  );
}
