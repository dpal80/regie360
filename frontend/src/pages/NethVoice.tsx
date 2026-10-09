import { useEffect, useState, type FormEvent } from "react";
import { api, put } from "../api";
import { useTelefono } from "../telefono";

type NethVoice = { attivo: boolean; cti_host: string; sip_host: string; sip_porta: string; certificato_ca: string };

const VUOTA: NethVoice = { attivo: true, cti_host: "", sip_host: "", sip_porta: "", certificato_ca: "" };

export default function NethVoicePagina() {
  const { ricarica } = useTelefono();
  const [config, setConfig] = useState<NethVoice>(VUOTA);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [inCorso, setInCorso] = useState(false);

  useEffect(() => {
    api<NethVoice>("/impostazioni/nethvoice")
      // Finché non è mai stata configurata, la spunta "attiva" parte accesa.
      .then((c) => setConfig(c.cti_host ? c : { ...c, attivo: true }))
      .catch((e) => setErrore(e.message));
  }, []);

  async function salva(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setAvviso("");
    setInCorso(true);
    try {
      setConfig(await put<NethVoice>("/impostazioni/nethvoice", config));
      await ricarica();
      setAvviso("Impostazioni salvate. Ogni operatore collega il suo telefono dalla pagina Telefono.");
    } catch (err) {
      setErrore((err as Error).message);
    } finally {
      setInCorso(false);
    }
  }

  return (
    <>
      <p className="tenue">
        Qui colleghi il CRM al centralino NethVoice, per chiamare dal browser con Phone Island. Poi ogni operatore
        collega il proprio telefono dalla pagina Telefono.
      </p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}
        <form className="scheda modulo" onSubmit={salva}>
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
    </>
  );
}
