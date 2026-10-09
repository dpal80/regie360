import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CHIAMATA_FINITA, useTelefono, type Telefonata } from "../telefono";
import { api, formatoData, formatoDataOra, post, STATI_CONTATTO, type ContattoRiga, type Voce } from "../api";

type Scheda = ContattoRiga & {
  campagna_stato: string;
  motivo: string | null;
  cliente_dati: { id: number; nominativo: string; codice: string | null; telefono_cellulare: string | null; telefono_fisso: string | null; email: string | null };
  veicolo_dati: { id: number; targa: string | null; marca: string | null; modello: string | null; data_immatricolazione: string | null; data_ultimo_passaggio: string | null };
  passaggi: { id: number; numero_or: string | null; sede: string | null; descrizione: string | null; data_apertura: string | null }[];
  chiamate: { id: number; inizio: string; operatore: string; esito: string | null }[];
  note: { id: number; testo: string; autore: string; creato_il: string }[];
  opportunita: { id: number; fase: string; titolare: string; data_appuntamento: string | null; descrizione: string | null }[];
};

const CHIAMATA_VUOTA = { esito_id: "", nota: "", data_richiamo: "" };
const OPPORTUNITA_VUOTA = { crea: false, data_appuntamento: "", sede_id: "", descrizione: "", ammontare: "" };

const iso = (locale: string) => (locale ? new Date(locale).toISOString() : null);

export default function Contatto() {
  const { id } = useParams();
  const naviga = useNavigate();
  const [scheda, setScheda] = useState<Scheda | null>(null);
  const [esiti, setEsiti] = useState<Voce[]>([]);
  const [sedi, setSedi] = useState<{ id: number; nome: string }[]>([]);
  const [chiamata, setChiamata] = useState(CHIAMATA_VUOTA);
  const [opportunita, setOpportunita] = useState(OPPORTUNITA_VUOTA);
  const [nota, setNota] = useState("");
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");
  const [inCorso, setInCorso] = useState(false);
  const { pronto, chiama } = useTelefono();
  // La telefonata appena chiusa su Phone Island: il suo ID e la durata finiscono sulla chiamata registrata.
  const [telefonata, setTelefonata] = useState<Telefonata | null>(null);

  useEffect(() => {
    const finita = (e: Event) => {
      setTelefonata((e as CustomEvent<Telefonata>).detail);
      document.getElementById("registra-chiamata")?.scrollIntoView({ behavior: "smooth", block: "center" });
    };
    window.addEventListener(CHIAMATA_FINITA, finita);
    return () => window.removeEventListener(CHIAMATA_FINITA, finita);
  }, []);

  const carica = () => api<Scheda>(`/contatti/${id}`).then(setScheda).catch((e) => setErrore(e.message));
  useEffect(() => {
    setScheda(null);
    setTelefonata(null);
    carica();
    api<Voce[]>("/elenchi/esito").then(setEsiti).catch(() => undefined);
    api<{ id: number; nome: string }[]>("/sedi").then(setSedi).catch(() => undefined);
  }, [id]);

  if (!scheda) return errore ? <div className="errore">{errore}</div> : <p className="tenue">Caricamento…</p>;

  const esito = esiti.find((e) => String(e.id) === chiamata.esito_id);
  const cliente = scheda.cliente_dati;
  const veicolo = scheda.veicolo_dati;
  const aperto = scheda.stato !== "chiuso" && scheda.campagna_stato === "attiva";

  // Con Phone Island collegato il numero si chiama dal CRM, altrimenti resta un normale collegamento tel:.
  const numero = (n: string) => (
    <>
      <a className="telefono" href={`tel:${n}`}>{n}</a>
      {pronto && aperto && <button className="primario chiama" onClick={() => chiama(n)}>Chiama</button>}
    </>
  );

  async function registra(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    setAvviso("");
    setInCorso(true);
    try {
      const r = await post<{ chiamata_id: number; stato: string }>(`/contatti/${id}/chiamate`, {
        esito_id: Number(chiamata.esito_id),
        nota: chiamata.nota || null,
        data_richiamo: esito?.effetto === "richiamo" ? iso(chiamata.data_richiamo) : null,
        unique_id: telefonata?.uniqueId ?? null,
        durata_secondi: telefonata?.durata ?? null,
        numero: telefonata?.numero || null,
      });
      setTelefonata(null);
      if (opportunita.crea) {
        await post("/opportunita", {
          cliente_id: cliente.id,
          veicolo_id: veicolo.id,
          chiamata_id: r.chiamata_id,
          data_appuntamento: iso(opportunita.data_appuntamento),
          sede_id: opportunita.sede_id ? Number(opportunita.sede_id) : null,
          descrizione: opportunita.descrizione || null,
          ammontare: opportunita.ammontare || null,
        });
      }
      setChiamata(CHIAMATA_VUOTA);
      setOpportunita(OPPORTUNITA_VUOTA);
      setAvviso(opportunita.crea ? "Chiamata e opportunità registrate." : "Chiamata registrata.");
      await carica();
    } catch (err) {
      setErrore((err as Error).message);
      await carica();
    } finally {
      setInCorso(false);
    }
  }

  async function aggiungiNota(e: FormEvent) {
    e.preventDefault();
    setErrore("");
    try {
      await post(`/clienti/${cliente.id}/note`, { testo: nota });
      setNota("");
      await carica();
    } catch (err) {
      setErrore((err as Error).message);
    }
  }

  async function prossimo() {
    setErrore("");
    try {
      const r = await post<{ contatto_id: number }>(`/campagne/${scheda!.campagna_id}/prossimo`);
      naviga(`/contatti/${r.contatto_id}`);
    } catch (err) {
      setErrore((err as Error).message);
    }
  }

  return (
    <>
      <Link to="/chiamate" className="indietro">‹ Le mie chiamate</Link>
      <div className="testata">
        <h1>{cliente.nominativo}</h1>
        <button onClick={prossimo}>Prossimo contatto ›</button>
      </div>
      <p className="tenue">
        {scheda.campagna}{scheda.motivo ? ` · ${scheda.motivo}` : ""} · {STATI_CONTATTO[scheda.stato]}
        {scheda.operatore ? ` · ${scheda.operatore}` : ""} · {scheda.tentativi} {scheda.tentativi === 1 ? "tentativo" : "tentativi"}
        {scheda.data_richiamo ? ` · richiamo ${formatoDataOra(scheda.data_richiamo)}` : ""}
      </p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}

      <div className="colonne">
        <section className="scheda">
          <h3>Cliente</h3>
          <dl className="dati">
            <dt>Cellulare</dt><dd>{cliente.telefono_cellulare && numero(cliente.telefono_cellulare)}</dd>
            <dt>Fisso</dt><dd>{cliente.telefono_fisso && numero(cliente.telefono_fisso)}</dd>
            <dt>E-mail</dt><dd>{cliente.email}</dd>
            <dt>Codice</dt><dd>{cliente.codice}</dd>
          </dl>
        </section>
        <section className="scheda">
          <h3>{veicolo.marca} {veicolo.modello} <span className="targa">{veicolo.targa}</span></h3>
          <dl className="dati">
            <dt>Immatricolazione</dt><dd>{formatoData(veicolo.data_immatricolazione)}</dd>
            <dt>Ultimo passaggio</dt><dd>{formatoData(veicolo.data_ultimo_passaggio)}</dd>
          </dl>
          {scheda.passaggi.map((p) => (
            <p key={p.id} className="riga-storia">
              <strong>{formatoData(p.data_apertura)}</strong> {p.sede ? `${p.sede} · ` : ""}{p.descrizione}
            </p>
          ))}
        </section>
      </div>

      {aperto ? (
        <form className="scheda modulo" id="registra-chiamata" onSubmit={registra}>
          <h3 className="larga">Registra la chiamata</h3>
          {telefonata && (
            <div className="messaggio-ok larga">
              Telefonata terminata{telefonata.durata ? ` (${Math.floor(telefonata.durata / 60)}:${String(telefonata.durata % 60).padStart(2, "0")})` : ""}: scegli l'esito e registra.
            </div>
          )}
          <label>
            Esito
            <select required value={chiamata.esito_id} onChange={(e) => setChiamata({ ...chiamata, esito_id: e.target.value })}>
              <option value="">Scegli…</option>
              {esiti.map((e) => <option key={e.id} value={e.id}>{e.nome}</option>)}
            </select>
          </label>
          {esito?.effetto === "richiamo" && (
            <label>
              Richiamare il
              <input type="datetime-local" value={chiamata.data_richiamo} onChange={(e) => setChiamata({ ...chiamata, data_richiamo: e.target.value })} />
            </label>
          )}
          {esito?.effetto === "escluso" && (
            <div className="errore larga">Con questo esito il cliente esce da tutte le liste e non verrà più richiamato.</div>
          )}
          <label className="larga">
            Nota
            <textarea rows={3} value={chiamata.nota} onChange={(e) => setChiamata({ ...chiamata, nota: e.target.value })} />
          </label>
          <label className="spunta larga">
            <input type="checkbox" checked={opportunita.crea} onChange={(e) => setOpportunita({ ...opportunita, crea: e.target.checked })} />
            Crea un'opportunità (appuntamento preso)
          </label>
          {opportunita.crea && (
            <>
              <label>
                Data appuntamento
                <input type="datetime-local" required value={opportunita.data_appuntamento} onChange={(e) => setOpportunita({ ...opportunita, data_appuntamento: e.target.value })} />
              </label>
              <label>
                Sede
                <select value={opportunita.sede_id} onChange={(e) => setOpportunita({ ...opportunita, sede_id: e.target.value })}>
                  <option value="">Non indicata</option>
                  {sedi.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
                </select>
              </label>
              <label>
                Ammontare previsto (€)
                <input type="number" min={0} step="0.01" value={opportunita.ammontare} onChange={(e) => setOpportunita({ ...opportunita, ammontare: e.target.value })} />
              </label>
              <label className="larga">
                Descrizione
                <input value={opportunita.descrizione} onChange={(e) => setOpportunita({ ...opportunita, descrizione: e.target.value })} placeholder="Tagliando e cambio gomme" />
              </label>
            </>
          )}
          <div className="azioni larga"><button type="submit" className="primario" disabled={inCorso}>Registra chiamata</button></div>
        </form>
      ) : (
        <p className="tenue">
          {scheda.stato === "chiuso" ? "Questo contatto è chiuso." : "La campagna è chiusa: non si possono registrare altre chiamate."}
        </p>
      )}

      <div className="colonne">
        <section>
          <h2>Note</h2>
          <form className="filtri" onSubmit={aggiungiNota}>
            <label className="largo">Nuova nota<input required value={nota} onChange={(e) => setNota(e.target.value)} /></label>
            <div className="azioni"><button type="submit">Aggiungi</button></div>
          </form>
          {scheda.note.map((n) => (
            <p key={n.id} className="riga-storia"><strong>{formatoDataOra(n.creato_il)} · {n.autore}</strong><br />{n.testo}</p>
          ))}
          {scheda.note.length === 0 && <p className="tenue">Nessuna nota.</p>}
        </section>
        <section>
          <h2>Chiamate</h2>
          {scheda.chiamate.map((c) => (
            <p key={c.id} className="riga-storia"><strong>{formatoDataOra(c.inizio)}</strong> {c.operatore} · {c.esito}</p>
          ))}
          {scheda.chiamate.length === 0 && <p className="tenue">Nessuna chiamata registrata.</p>}
          <h2>Opportunità</h2>
          {scheda.opportunita.map((o) => (
            <p key={o.id} className="riga-storia">
              <strong>{o.fase}</strong> {o.data_appuntamento ? `· ${formatoDataOra(o.data_appuntamento)} ` : ""}· {o.titolare}
              {o.descrizione ? <><br />{o.descrizione}</> : null}
            </p>
          ))}
          {scheda.opportunita.length === 0 && <p className="tenue">Nessuna opportunità.</p>}
        </section>
      </div>
    </>
  );
}
