// Phone Island (NethVoice): carica il widget, fa partire le chiamate e avvisa le pagine quando finiscono.
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, query } from "./api";

export type StatoTelefono = { attivo: boolean; collegato: boolean; interno: string | null; data_config: string | null };

// Quello che serve al CRM di una telefonata, preso dall'evento phone-island-conversations.
export type Telefonata = { uniqueId: string; numero: string; nome: string; direzione: "in" | "out"; durata: number };

type Chiamante = { nominativo: string; cliente_id: number | null; contatto_id: number | null };

type Telefono = {
  stato: StatoTelefono | null;
  pronto: boolean; // si può chiamare dal CRM
  chiama: (numero: string) => void;
  ricarica: () => Promise<void>;
};

const Contesto = createContext<Telefono>({ stato: null, pronto: false, chiama: () => undefined, ricarica: async () => undefined });

export const useTelefono = () => useContext(Contesto);

/** Evento del CRM, lanciato quando Phone Island chiude una telefonata: detail = Telefonata. */
export const CHIAMATA_FINITA = "crm-chiamata-finita";

let widgetCaricato = false;

function caricaWidget(dataConfig: string) {
  if (widgetCaricato) return;
  widgetCaricato = true;
  const stile = document.createElement("link");
  stile.rel = "stylesheet";
  stile.href = "/phone-island/index.widget.css";
  document.head.appendChild(stile);
  // Il widget si aggancia agli elementi .phone-island che trova quando parte: prima il contenitore, poi lo script.
  const contenitore = document.createElement("div");
  contenitore.className = "phone-island";
  contenitore.setAttribute("data-config", dataConfig);
  document.body.appendChild(contenitore);
  const script = document.createElement("script");
  script.src = "/phone-island/index.widget.js";
  document.body.appendChild(script);
}

// L'evento porta { utente: { conversations: { id: {...} } } }: qui si prende la telefonata in corso, se c'è.
function leggiTelefonata(detail: unknown): Telefonata | null {
  for (const utente of Object.values((detail ?? {}) as Record<string, { conversations?: Record<string, Record<string, unknown>> }>)) {
    for (const c of Object.values(utente?.conversations ?? {})) {
      if (!c?.uniqueId) continue;
      return {
        uniqueId: String(c.uniqueId),
        numero: String(c.counterpartNum ?? ""),
        nome: String(c.counterpartName ?? ""),
        direzione: c.direction === "in" ? "in" : "out",
        durata: Number(c.duration) || 0,
      };
    }
  }
  return null;
}

export function TelefonoProvider({ children }: { children: ReactNode }) {
  const [stato, setStato] = useState<StatoTelefono | null>(null);
  const [inArrivo, setInArrivo] = useState<{ telefonata: Telefonata; clienti: Chiamante[] } | null>(null);
  const corrente = useRef<Telefonata | null>(null);

  const ricarica = useCallback(async () => {
    setStato(await api<StatoTelefono>("/telefonia/stato").catch(() => null));
  }, []);
  useEffect(() => {
    ricarica();
  }, [ricarica]);

  const dataConfig = stato?.data_config ?? null;
  useEffect(() => {
    if (!dataConfig) return;
    caricaWidget(dataConfig);

    const conversazioni = (e: Event) => {
      const t = leggiTelefonata((e as CustomEvent).detail);
      if (!t) return;
      const nuova = corrente.current?.uniqueId !== t.uniqueId;
      corrente.current = t;
      if (nuova && t.direzione === "in" && t.numero) {
        api<{ clienti: Chiamante[] }>(`/telefonia/cerca${query({ numero: t.numero })}`)
          .then((r) => setInArrivo({ telefonata: t, clienti: r.clienti }))
          .catch(() => setInArrivo({ telefonata: t, clienti: [] }));
      }
    };
    const finita = () => {
      const t = corrente.current;
      corrente.current = null;
      if (t) window.dispatchEvent(new CustomEvent(CHIAMATA_FINITA, { detail: t }));
    };
    window.addEventListener("phone-island-conversations", conversazioni);
    window.addEventListener("phone-island-call-ended", finita);
    return () => {
      window.removeEventListener("phone-island-conversations", conversazioni);
      window.removeEventListener("phone-island-call-ended", finita);
    };
  }, [dataConfig]);

  const chiama = useCallback((numero: string) => {
    window.dispatchEvent(new CustomEvent("phone-island-call-start", { detail: { number: numero.replace(/[^\d+*#]/g, "") } }));
  }, []);

  return (
    <Contesto.Provider value={{ stato, pronto: dataConfig !== null, chiama, ricarica }}>
      {inArrivo && (
        <div className="chiamata-in-arrivo">
          <strong>Chiamata da {inArrivo.telefonata.numero}</strong>
          {inArrivo.clienti.length === 0 && <span>Numero non presente tra i clienti</span>}
          {inArrivo.clienti.map((c, i) => (
            <span key={i}>
              {c.contatto_id ? <Link to={`/contatti/${c.contatto_id}`}>{c.nominativo}</Link>
                : c.cliente_id ? <Link to={`/clienti/${c.cliente_id}`}>{c.nominativo}</Link>
                : c.nominativo}
            </span>
          ))}
          <button onClick={() => setInArrivo(null)}>Chiudi</button>
        </div>
      )}
      {children}
    </Contesto.Provider>
  );
}
