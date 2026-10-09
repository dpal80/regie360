import { useEffect, useState, type FormEvent } from "react";
import { api, patch, post, type Voce } from "../api";

type Elenco = { chiave: string; titolo: string; aiuto: string; effetti?: Record<string, string> };

const ELENCHI: Elenco[] = [
  {
    chiave: "esito", titolo: "Esiti chiamata",
    aiuto: "Cosa sceglie l'operatore a fine telefonata, e cosa succede al contatto.",
    effetti: { richiamo: "Resta da richiamare", chiuso: "Esce dalla lista", escluso: "Esce e non va più richiamato" },
  },
  { chiave: "motivo_richiamo", titolo: "Motivi di richiamo", aiuto: "Il motivo per cui nasce una campagna." },
  {
    chiave: "fase_opportunita", titolo: "Fasi opportunità",
    aiuto: "Le tappe di un'opportunità, dall'appuntamento alla chiusura.",
    effetti: { aperta: "In corso", vinta: "Chiusa vinta", persa: "Chiusa persa" },
  },
  { chiave: "motivo_perdita", titolo: "Motivi di perdita", aiuto: "Perché un'opportunità si chiude come persa." },
  { chiave: "prodotto", titolo: "Prodotti", aiuto: "Cosa si vende in più oltre all'intervento richiesto." },
];

export default function Elenchi() {
  const [elenco, setElenco] = useState(ELENCHI[0]);
  const [voci, setVoci] = useState<Voce[]>([]);
  const [nuova, setNuova] = useState({ nome: "", effetto: "", famiglia: "" });
  const [errore, setErrore] = useState("");

  const carica = () =>
    api<Voce[]>(`/elenchi/${elenco.chiave}?tutte=true`).then(setVoci).catch((e) => setErrore(e.message));
  useEffect(() => {
    setVoci([]);
    setNuova({ nome: "", effetto: "", famiglia: "" });
    carica();
  }, [elenco]);

  async function azione(f: () => Promise<unknown>) {
    setErrore("");
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
      await post(`/elenchi/${elenco.chiave}`, {
        nome: nuova.nome, effetto: nuova.effetto || null, famiglia: nuova.famiglia || null,
      });
      setNuova({ nome: "", effetto: "", famiglia: "" });
    });
  }

  const prodotti = elenco.chiave === "prodotto";

  return (
    <>
      <h1>Elenchi</h1>
      <div className="schede-menu">
        {ELENCHI.map((e) => (
          <button key={e.chiave} className={e.chiave === elenco.chiave ? "primario" : ""} onClick={() => setElenco(e)}>
            {e.titolo}
          </button>
        ))}
      </div>
      <p className="tenue">{elenco.aiuto} Le voci già usate non si cancellano: si disattivano.</p>
      {errore && <div className="errore">{errore}</div>}
      <form className="filtri scheda" onSubmit={aggiungi}>
        <label>Nuova voce<input required value={nuova.nome} onChange={(e) => setNuova({ ...nuova, nome: e.target.value })} /></label>
        {elenco.effetti && (
          <label>
            Cosa succede
            <select required value={nuova.effetto} onChange={(e) => setNuova({ ...nuova, effetto: e.target.value })}>
              <option value="">Scegli…</option>
              {Object.entries(elenco.effetti).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        )}
        {prodotti && <label>Famiglia<input value={nuova.famiglia} onChange={(e) => setNuova({ ...nuova, famiglia: e.target.value })} /></label>}
        <div className="azioni"><button className="primario" type="submit">Aggiungi</button></div>
      </form>
      <table>
        <thead>
          <tr><th>Voce</th>{elenco.effetti && <th>Cosa succede</th>}{prodotti && <th>Famiglia</th>}<th>Stato</th><th></th></tr>
        </thead>
        <tbody>
          {voci.map((v) => (
            <tr key={v.id} className={v.attivo ? "" : "spento"}>
              <td>
                <input
                  className="ampio"
                  defaultValue={v.nome}
                  onBlur={(e) => e.target.value.trim() && e.target.value !== v.nome && azione(() => patch(`/elenchi/voci/${v.id}`, { nome: e.target.value }))}
                />
              </td>
              {elenco.effetti && (
                <td>
                  <select value={v.effetto ?? ""} onChange={(e) => azione(() => patch(`/elenchi/voci/${v.id}`, { effetto: e.target.value }))}>
                    {Object.entries(elenco.effetti).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
                  </select>
                </td>
              )}
              {prodotti && (
                <td>
                  <input
                    defaultValue={v.famiglia ?? ""}
                    onBlur={(e) => e.target.value !== (v.famiglia ?? "") && azione(() => patch(`/elenchi/voci/${v.id}`, { famiglia: e.target.value }))}
                  />
                </td>
              )}
              <td>{v.attivo ? "Attiva" : "Disattivata"}</td>
              <td>
                <div className="azioni-riga">
                  <button onClick={() => azione(() => patch(`/elenchi/voci/${v.id}`, { attivo: !v.attivo }))}>
                    {v.attivo ? "Disattiva" : "Riattiva"}
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {voci.length === 0 && <tr><td colSpan={5} className="vuoto">Nessuna voce in questo elenco</td></tr>}
        </tbody>
      </table>
    </>
  );
}
