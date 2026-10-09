import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, eResponsabile } from "../api";
import { useAuth } from "../auth";

type Riepilogo = { clienti: number; veicoli: number; passaggi: number };

export default function Home() {
  const { utente } = useAuth();
  const [riepilogo, setRiepilogo] = useState<Riepilogo | null>(null);
  const responsabile = eResponsabile(utente);

  useEffect(() => {
    if (responsabile) api<Riepilogo>("/riepilogo").then(setRiepilogo).catch(() => undefined);
  }, [responsabile]);

  return (
    <>
      <h1>Ciao {utente?.nome}</h1>
      {utente && !utente.totp_attivo && (
        <p className="consiglio">
          Proteggi il tuo accesso: attiva la verifica in due passaggi da <Link to="/account">Il mio account</Link>. È
          consigliata e richiede un minuto.
        </p>
      )}
      {responsabile ? (
        <>
          <div className="tessere">
            <Link to="/clienti" className="tessera">
              <span>{riepilogo?.clienti.toLocaleString("it-IT") ?? "…"}</span>clienti
            </Link>
            <Link to="/veicoli" className="tessera">
              <span>{riepilogo?.veicoli.toLocaleString("it-IT") ?? "…"}</span>veicoli
            </Link>
            <div className="tessera">
              <span>{riepilogo?.passaggi.toLocaleString("it-IT") ?? "…"}</span>passaggi in officina
            </div>
          </div>
          {riepilogo?.clienti === 0 && (
            <p>
              Il CRM è vuoto: parti da <Link to="/importa">Importa dati</Link> per caricare il file Excel.
            </p>
          )}
        </>
      ) : (
        <p>Le campagne dei tuoi team e i contatti da chiamare sono in <Link to="/chiamate">Le mie chiamate</Link>.</p>
      )}
    </>
  );
}
