import { useEffect, useState, type FormEvent } from "react";
import { api, formatoDataOra, patch, query, type Pagina, type Voce } from "../api";
import { useAuth } from "../auth";
import Paginatore from "../components/Paginatore";

type Opportunita = {
  id: number;
  titolare: string;
  cliente: string;
  telefono: string | null;
  veicolo: string | null;
  targa: string | null;
  fase_id: number;
  fase: string;
  fase_effetto: string | null;
  data_appuntamento: string | null;
  sede_id: number | null;
  sede: string | null;
  descrizione: string | null;
  ammontare: number | null;
  vendita_aggiuntiva: boolean;
  prezzo_vendita: number | null;
  prodotto_id: number | null;
  prodotto: string | null;
  motivo_perdita_id: number | null;
  motivo_perdita: string | null;
  note_perdita: string | null;
};

type Modulo = {
  fase_id: string; data_appuntamento: string; sede_id: string; descrizione: string; ammontare: string;
  vendita_aggiuntiva: boolean; prezzo_vendita: string; prodotto_id: string; motivo_perdita_id: string; note_perdita: string;
};

const euro = (n: number | null) => (n === null ? "" : n.toLocaleString("it-IT", { style: "currency", currency: "EUR" }));

// Da data ISO a valore per <input type="datetime-local">, nell'ora del PC.
function perCampo(d: string | null): string {
  if (!d) return "";
  const x = new Date(d);
  return new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function OpportunitaPagina() {
  const { utente } = useAuth();
  const responsabile = utente?.ruolo === "responsabile";
  const [dati, setDati] = useState<Pagina<Opportunita> | null>(null);
  const [fasi, setFasi] = useState<Voce[]>([]);
  const [prodotti, setProdotti] = useState<Voce[]>([]);
  const [motivi, setMotivi] = useState<Voce[]>([]);
  const [sedi, setSedi] = useState<{ id: number; nome: string }[]>([]);
  const [faseFiltro, setFaseFiltro] = useState("");
  const [pagina, setPagina] = useState(1);
  const [aperta, setAperta] = useState<Opportunita | null>(null);
  const [modulo, setModulo] = useState<Modulo | null>(null);
  const [errore, setErrore] = useState("");

  const carica = () =>
    api<Pagina<Opportunita>>(`/opportunita${query({ fase_id: faseFiltro, pagina })}`).then(setDati).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
  }, [faseFiltro, pagina]);
  useEffect(() => {
    api<Voce[]>("/elenchi/fase_opportunita").then(setFasi).catch(() => undefined);
    api<Voce[]>("/elenchi/prodotto").then(setProdotti).catch(() => undefined);
    api<Voce[]>("/elenchi/motivo_perdita").then(setMotivi).catch(() => undefined);
    api<{ id: number; nome: string }[]>("/sedi").then(setSedi).catch(() => undefined);
  }, []);

  function apri(o: Opportunita) {
    setErrore("");
    setAperta(o);
    setModulo({
      fase_id: String(o.fase_id),
      data_appuntamento: perCampo(o.data_appuntamento),
      sede_id: o.sede_id ? String(o.sede_id) : "",
      descrizione: o.descrizione ?? "",
      ammontare: o.ammontare === null ? "" : String(o.ammontare),
      vendita_aggiuntiva: o.vendita_aggiuntiva,
      prezzo_vendita: o.prezzo_vendita === null ? "" : String(o.prezzo_vendita),
      prodotto_id: o.prodotto_id ? String(o.prodotto_id) : "",
      motivo_perdita_id: o.motivo_perdita_id ? String(o.motivo_perdita_id) : "",
      note_perdita: o.note_perdita ?? "",
    });
  }

  const numero = (v: string) => (v ? Number(v) : null);
  const persa = modulo !== null && fasi.find((f) => String(f.id) === modulo.fase_id)?.effetto === "persa";

  async function salva(e: FormEvent) {
    e.preventDefault();
    if (!aperta || !modulo) return;
    setErrore("");
    try {
      await patch(`/opportunita/${aperta.id}`, {
        fase_id: Number(modulo.fase_id),
        data_appuntamento: modulo.data_appuntamento ? new Date(modulo.data_appuntamento).toISOString() : null,
        sede_id: numero(modulo.sede_id),
        descrizione: modulo.descrizione || null,
        ammontare: modulo.ammontare || null,
        vendita_aggiuntiva: modulo.vendita_aggiuntiva,
        prezzo_vendita: modulo.prezzo_vendita || null,
        prodotto_id: numero(modulo.prodotto_id),
        ...(persa ? { motivo_perdita_id: numero(modulo.motivo_perdita_id), note_perdita: modulo.note_perdita || null } : {}),
      });
      setAperta(null);
      setModulo(null);
      await carica();
    } catch (err) {
      setErrore((err as Error).message);
    }
  }

  const imposta = (k: keyof Modulo) => (e: { target: { value: string } }) => modulo && setModulo({ ...modulo, [k]: e.target.value });

  return (
    <>
      <h1>Opportunità</h1>
      {!responsabile && <p className="tenue">Qui vedi le opportunità che hai creato tu.</p>}
      {errore && <div className="errore">{errore}</div>}
      {aperta && modulo && (
        <form className="scheda modulo" onSubmit={salva}>
          <h3 className="larga">{aperta.cliente} {aperta.targa && <span className="targa">{aperta.targa}</span>}</h3>
          <label>
            Fase
            <select value={modulo.fase_id} onChange={imposta("fase_id")}>
              {fasi.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
            </select>
          </label>
          <label>Data appuntamento<input type="datetime-local" value={modulo.data_appuntamento} onChange={imposta("data_appuntamento")} /></label>
          <label>
            Sede
            <select value={modulo.sede_id} onChange={imposta("sede_id")}>
              <option value="">Non indicata</option>
              {sedi.map((s) => <option key={s.id} value={s.id}>{s.nome}</option>)}
            </select>
          </label>
          <label>Ammontare (€)<input type="number" min={0} step="0.01" value={modulo.ammontare} onChange={imposta("ammontare")} /></label>
          <label className="larga">Descrizione<input value={modulo.descrizione} onChange={imposta("descrizione")} /></label>
          <label className="spunta larga">
            <input type="checkbox" checked={modulo.vendita_aggiuntiva} onChange={(e) => setModulo({ ...modulo, vendita_aggiuntiva: e.target.checked })} />
            Vendita aggiuntiva
          </label>
          {modulo.vendita_aggiuntiva && (
            <>
              <label>
                Prodotto
                <select value={modulo.prodotto_id} onChange={imposta("prodotto_id")}>
                  <option value="">Non indicato</option>
                  {prodotti.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
                </select>
              </label>
              <label>Prezzo di vendita (€)<input type="number" min={0} step="0.01" value={modulo.prezzo_vendita} onChange={imposta("prezzo_vendita")} /></label>
            </>
          )}
          {persa && (
            <>
              <label>
                Motivo della perdita
                <select required value={modulo.motivo_perdita_id} onChange={imposta("motivo_perdita_id")}>
                  <option value="">Scegli…</option>
                  {motivi.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
                </select>
              </label>
              <label className="larga">Note sulla perdita<input value={modulo.note_perdita} onChange={imposta("note_perdita")} /></label>
            </>
          )}
          <div className="azioni larga">
            <button type="button" onClick={() => { setAperta(null); setModulo(null); }}>Annulla</button>
            <button type="submit" className="primario">Salva</button>
          </div>
        </form>
      )}
      <div className="filtri">
        <label>
          Fase
          <select value={faseFiltro} onChange={(e) => { setFaseFiltro(e.target.value); setPagina(1); }}>
            <option value="">Tutte</option>
            {fasi.map((f) => <option key={f.id} value={f.id}>{f.nome}</option>)}
          </select>
        </label>
      </div>
      <table>
        <thead>
          <tr>
            <th>Appuntamento</th><th>Cliente</th><th>Telefono</th><th>Veicolo</th><th>Sede</th><th>Fase</th>
            <th className="num">Ammontare</th>{responsabile && <th>Titolare</th>}<th></th>
          </tr>
        </thead>
        <tbody>
          {dati?.elementi.map((o) => (
            <tr key={o.id} className={o.fase_effetto === "persa" ? "spento" : ""}>
              <td>{formatoDataOra(o.data_appuntamento)}</td>
              <td>{o.cliente}{o.descrizione && <><br /><small className="tenue">{o.descrizione}</small></>}</td>
              <td>{o.telefono}</td>
              <td><span className="targa">{o.targa}</span> {o.veicolo}</td>
              <td>{o.sede}</td>
              <td>{o.fase}{o.motivo_perdita && <><br /><small className="tenue">{o.motivo_perdita}</small></>}</td>
              <td className="num">{euro(o.ammontare)}</td>
              {responsabile && <td>{o.titolare}</td>}
              <td><div className="azioni-riga"><button onClick={() => apri(o)}>Modifica</button></div></td>
            </tr>
          ))}
          {dati && dati.elementi.length === 0 && <tr><td colSpan={9} className="vuoto">Nessuna opportunità</td></tr>}
        </tbody>
      </table>
      {dati && <Paginatore pagina={pagina} perPagina={dati.per_pagina} totale={dati.totale} onCambia={setPagina} />}
    </>
  );
}
