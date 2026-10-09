import { useEffect, useState } from "react";
import { api, ErroreApi, formatoDataOra, post } from "../api";

type Campo = { chiave: string; etichetta: string };

type Caricato = {
  id: number;
  nome_file: string;
  intestazioni: string[];
  righe_totali: number;
  mappatura: string[];
  mappatura_salvata: string | null;
  esempio: unknown[][];
};

type Problema = { riga: number; tipo: "errore" | "avviso"; messaggio: string };

type Anteprima = {
  righe_totali: number;
  righe_valide: number;
  righe_scartate: number;
  righe_con_avvisi: number;
  clienti_distinti: number;
  veicoli_distinti: number;
  problemi: Problema[];
};

type Esito = {
  id: number;
  nome_file: string;
  stato: string;
  righe_totali: number;
  clienti_nuovi: number;
  clienti_aggiornati: number;
  veicoli_nuovi: number;
  veicoli_aggiornati: number;
  passaggi_nuovi: number;
  righe_scartate: number;
  creato_il: string;
  completato_il: string | null;
  creato_da: string | null;
};

type Passo = "carica" | "mappa" | "anteprima" | "fatto";

export default function Importa() {
  const [passo, setPasso] = useState<Passo>("carica");
  const [campi, setCampi] = useState<Campo[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [caricato, setCaricato] = useState<Caricato | null>(null);
  const [mappatura, setMappatura] = useState<string[]>([]);
  const [anteprima, setAnteprima] = useState<Anteprima | null>(null);
  const [salvaCome, setSalvaCome] = useState("");
  const [esito, setEsito] = useState<Esito | null>(null);
  const [storico, setStorico] = useState<Esito[]>([]);
  const [lavoro, setLavoro] = useState(false);
  const [errore, setErrore] = useState("");

  const aggiornaStorico = () => api<Esito[]>("/importazioni").then(setStorico).catch(() => undefined);

  useEffect(() => {
    api<{ campi: Campo[]; speciali: Campo[] }>("/importazioni/campi").then((r) => setCampi([...r.campi, ...r.speciali]));
    aggiornaStorico();
  }, []);

  async function esegui(azione: () => Promise<void>) {
    setErrore("");
    setLavoro(true);
    try {
      await azione();
    } catch (e) {
      setErrore(e instanceof ErroreApi ? e.message : "Operazione non riuscita");
    } finally {
      setLavoro(false);
    }
  }

  const carica = () =>
    esegui(async () => {
      if (!file) return;
      const fd = new FormData();
      fd.append("file", file);
      const r = await api<Caricato>("/importazioni", { method: "POST", body: fd });
      setCaricato(r);
      setMappatura(r.mappatura);
      setSalvaCome(r.mappatura_salvata ?? "Export officina");
      setPasso("mappa");
    });

  const controlla = () =>
    esegui(async () => {
      setAnteprima(await post<Anteprima>(`/importazioni/${caricato!.id}/anteprima`, { mappatura }));
      setPasso("anteprima");
    });

  const conferma = () =>
    esegui(async () => {
      setEsito(await post<Esito>(`/importazioni/${caricato!.id}/conferma`, { mappatura, salva_come: salvaCome || null }));
      setPasso("fatto");
      aggiornaStorico();
    });

  const ricomincia = async () => {
    if (caricato && passo !== "fatto") {
      await api(`/importazioni/${caricato.id}`, { method: "DELETE" }).catch(() => undefined);
    }
    setPasso("carica");
    setFile(null);
    setCaricato(null);
    setAnteprima(null);
    setEsito(null);
    setErrore("");
  };

  const usati = new Map<string, number>();
  mappatura.forEach((m) => usati.set(m, (usati.get(m) ?? 0) + 1));

  return (
    <>
      <h1>Importa dati</h1>
      <ol className="passi">
        <li className={passo === "carica" ? "attivo" : ""}>Carica il file</li>
        <li className={passo === "mappa" ? "attivo" : ""}>Abbina le colonne</li>
        <li className={passo === "anteprima" ? "attivo" : ""}>Controlla</li>
        <li className={passo === "fatto" ? "attivo" : ""}>Fatto</li>
      </ol>
      {errore && <div className="errore">{errore}</div>}

      {passo === "carica" && (
        <section className="scheda">
          <p>Carica il file Excel esportato dal gestionale (.xlsx, .xls o .csv). Ogni riga è un veicolo.</p>
          <input type="file" accept=".xlsx,.xls,.csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <div className="azioni">
            <button className="primario" disabled={!file || lavoro} onClick={carica}>
              {lavoro ? "Lettura del file…" : "Carica"}
            </button>
          </div>
        </section>
      )}

      {passo === "mappa" && caricato && (
        <section className="scheda">
          <p>
            <strong>{caricato.nome_file}</strong>: {caricato.righe_totali} righe, {caricato.intestazioni.length} colonne.
            {caricato.mappatura_salvata && <> Ho riusato la mappatura «{caricato.mappatura_salvata}».</>}
          </p>
          <table>
            <thead>
              <tr><th>Colonna del file</th><th>Esempi</th><th>Campo del CRM</th></tr>
            </thead>
            <tbody>
              {caricato.intestazioni.map((h, i) => {
                const doppio = !["extra", "ignora"].includes(mappatura[i]) && (usati.get(mappatura[i]) ?? 0) > 1;
                return (
                  <tr key={i}>
                    <td><strong>{h}</strong></td>
                    <td className="esempi">
                      {caricato.esempio.slice(0, 3).map((r) => r[i]).filter((v) => v !== null && v !== undefined).map(String).join(" · ")}
                    </td>
                    <td>
                      <select
                        value={mappatura[i]}
                        className={doppio ? "sbagliato" : ""}
                        onChange={(e) => setMappatura(mappatura.map((m, j) => (j === i ? e.target.value : m)))}
                      >
                        {campi.map((c) => <option key={c.chiave} value={c.chiave}>{c.etichetta}</option>)}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="azioni">
            <button onClick={ricomincia}>Annulla</button>
            <button className="primario" disabled={lavoro} onClick={controlla}>
              {lavoro ? "Controllo…" : "Controlla i dati"}
            </button>
          </div>
        </section>
      )}

      {passo === "anteprima" && anteprima && (
        <section className="scheda">
          <div className="tessere">
            <div className="tessera"><span>{anteprima.righe_valide}</span>righe da importare</div>
            <div className="tessera"><span>{anteprima.clienti_distinti}</span>clienti</div>
            <div className="tessera"><span>{anteprima.veicoli_distinti}</span>veicoli</div>
            <div className={`tessera ${anteprima.righe_scartate ? "rossa" : ""}`}><span>{anteprima.righe_scartate}</span>righe scartate</div>
            <div className={`tessera ${anteprima.righe_con_avvisi ? "arancio" : ""}`}><span>{anteprima.righe_con_avvisi}</span>righe con avvisi</div>
          </div>
          {anteprima.problemi.length > 0 && (
            <>
              <h3>Cosa ho trovato</h3>
              <ul className="problemi">
                {anteprima.problemi.slice(0, 200).map((p, i) => (
                  <li key={i} className={p.tipo}>
                    Riga {p.riga}: {p.messaggio}
                    {p.tipo === "errore" && " (la riga non verrà importata)"}
                  </li>
                ))}
              </ul>
            </>
          )}
          <label className="salva">
            Salva questo abbinamento come
            <input value={salvaCome} onChange={(e) => setSalvaCome(e.target.value)} placeholder="Nome (facoltativo)" />
          </label>
          <div className="azioni">
            <button onClick={() => setPasso("mappa")}>‹ Cambia abbinamento</button>
            <button onClick={ricomincia}>Annulla</button>
            <button className="primario" disabled={lavoro || anteprima.righe_valide === 0} onClick={conferma}>
              {lavoro ? "Importazione in corso…" : `Importa ${anteprima.righe_valide} righe`}
            </button>
          </div>
        </section>
      )}

      {passo === "fatto" && esito && (
        <section className="scheda">
          <h3>Import completato</h3>
          <p>
            Clienti: {esito.clienti_nuovi} nuovi, {esito.clienti_aggiornati} aggiornati. Veicoli: {esito.veicoli_nuovi} nuovi,{" "}
            {esito.veicoli_aggiornati} aggiornati. Passaggi in officina nuovi: {esito.passaggi_nuovi}. Righe scartate:{" "}
            {esito.righe_scartate}.
          </p>
          <div className="azioni">
            <button className="primario" onClick={ricomincia}>Importa un altro file</button>
          </div>
        </section>
      )}

      <h2>Import precedenti</h2>
      <table>
        <thead>
          <tr>
            <th>Data</th><th>File</th><th>Da</th><th>Stato</th>
            <th className="num">Clienti nuovi</th><th className="num">Veicoli nuovi</th><th className="num">Scartate</th>
          </tr>
        </thead>
        <tbody>
          {storico.map((s) => (
            <tr key={s.id}>
              <td>{formatoDataOra(s.completato_il ?? s.creato_il)}</td>
              <td>{s.nome_file}</td>
              <td>{s.creato_da}</td>
              <td>{s.stato === "completato" ? "Completato" : "In corso"}</td>
              <td className="num">{s.clienti_nuovi}</td>
              <td className="num">{s.veicoli_nuovi}</td>
              <td className="num">{s.righe_scartate}</td>
            </tr>
          ))}
          {storico.length === 0 && <tr><td colSpan={7} className="vuoto">Nessun import ancora</td></tr>}
        </tbody>
      </table>
    </>
  );
}
