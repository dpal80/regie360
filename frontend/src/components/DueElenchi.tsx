import { useState } from "react";

export type Voce = { id: number; nome: string; nota?: string };

type Props = {
  voci: Voce[];
  scelti: number[];
  onCambia: (scelti: number[]) => void;
  titoloDisponibili: string;
  titoloScelti: string;
};

// Due elenchi affiancati: a sinistra quello che c'è, a destra quello che si è scelto, e in mezzo le frecce.
export default function DueElenchi({ voci, scelti, onCambia, titoloDisponibili, titoloScelti }: Props) {
  const [evidenziati, setEvidenziati] = useState<number[]>([]);
  const [cerca, setCerca] = useState("");

  const testo = cerca.trim().toLowerCase();
  const disponibili = voci.filter((v) => !scelti.includes(v.id) && v.nome.toLowerCase().includes(testo));
  // A destra l'ordine è quello dell'elenco completo, non quello in cui si è cliccato.
  const selezionati = voci.filter((v) => scelti.includes(v.id));
  const daAggiungere = disponibili.filter((v) => evidenziati.includes(v.id)).map((v) => v.id);
  const daTogliere = selezionati.filter((v) => evidenziati.includes(v.id)).map((v) => v.id);

  function cambia(nuovi: number[]) {
    onCambia(nuovi);
    setEvidenziati([]);
  }
  const aggiungi = (ids: number[]) => cambia([...scelti, ...ids]);
  const togli = (ids: number[]) => cambia(scelti.filter((id) => !ids.includes(id)));
  const evidenzia = (id: number) =>
    setEvidenziati(evidenziati.includes(id) ? evidenziati.filter((x) => x !== id) : [...evidenziati, id]);

  const elenco = (lista: Voce[], vuoto: string, doppioClic: (id: number) => void) => (
    <ul className="lista-scelta" role="listbox" aria-multiselectable="true">
      {lista.map((v) => (
        <li
          key={v.id}
          role="option"
          aria-selected={evidenziati.includes(v.id)}
          tabIndex={0}
          className={evidenziati.includes(v.id) ? "evidenziato" : ""}
          onClick={() => evidenzia(v.id)}
          onDoubleClick={() => doppioClic(v.id)}
          onKeyDown={(e) => {
            if (e.key === " ") { e.preventDefault(); evidenzia(v.id); }
            if (e.key === "Enter") { e.preventDefault(); doppioClic(v.id); }
          }}
        >
          {v.nome} {v.nota && <small className="tenue">({v.nota})</small>}
        </li>
      ))}
      {lista.length === 0 && <li className="vuota">{vuoto}</li>}
    </ul>
  );

  return (
    <div className="due-elenchi">
      <div>
        <div className="testata">
          <strong>{titoloDisponibili} ({disponibili.length})</strong>
          <input value={cerca} onChange={(e) => setCerca(e.target.value)} placeholder="Cerca per nome" />
        </div>
        {elenco(disponibili, testo ? "Nessuno con questo nome" : "Sono già tutti a destra", (id) => aggiungi([id]))}
      </div>
      <div className="frecce">
        <button type="button" title="Aggiungi tutti" disabled={disponibili.length === 0} onClick={() => aggiungi(disponibili.map((v) => v.id))}>»</button>
        <button type="button" title="Aggiungi i selezionati" disabled={daAggiungere.length === 0} onClick={() => aggiungi(daAggiungere)}>›</button>
        <button type="button" title="Togli i selezionati" disabled={daTogliere.length === 0} onClick={() => togli(daTogliere)}>‹</button>
        <button type="button" title="Togli tutti" disabled={selezionati.length === 0} onClick={() => togli(selezionati.map((v) => v.id))}>«</button>
      </div>
      <div>
        <div className="testata"><strong>{titoloScelti} ({selezionati.length})</strong></div>
        {elenco(selezionati, "Ancora nessuno: sceglili a sinistra", (id) => togli([id]))}
      </div>
    </div>
  );
}
