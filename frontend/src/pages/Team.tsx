import { useEffect, useState, type FormEvent } from "react";
import { api, cancella, patch, post, RUOLI, type Ruolo } from "../api";
import DueElenchi from "../components/DueElenchi";

type Persona = { id: number; nome: string; ruolo: Ruolo; attivo: boolean };
type Team = { id: number; nome: string; attivo: boolean; membri: Persona[]; campagne: number };

// Il modulo aperto: un team nuovo (id null) oppure uno esistente in modifica.
type Modulo = { id: number | null; nome: string; membri: number[] };

export default function TeamPagina() {
  const [team, setTeam] = useState<Team[]>([]);
  const [persone, setPersone] = useState<Persona[]>([]);
  const [modulo, setModulo] = useState<Modulo | null>(null);
  const [errore, setErrore] = useState("");
  const [avviso, setAvviso] = useState("");

  const carica = () => api<Team[]>("/team").then(setTeam).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
    api<Persona[]>("/utenti")
      .then((u) => setPersone(u.filter((x) => x.attivo).sort((a, b) => Number(a.ruolo !== "operatore") - Number(b.ruolo !== "operatore") || a.nome.localeCompare(b.nome))))
      .catch(() => undefined);
  }, []);

  async function azione(f: () => Promise<unknown>, fatto = "") {
    setErrore("");
    setAvviso("");
    try {
      await f();
      await carica();
      setAvviso(fatto);
    } catch (e) {
      setErrore((e as Error).message);
    }
  }

  function apri(t: Team | null) {
    setErrore("");
    setAvviso("");
    setModulo(t ? { id: t.id, nome: t.nome, membri: t.membri.map((m) => m.id) } : { id: null, nome: "", membri: [] });
  }

  function salva(e: FormEvent) {
    e.preventDefault();
    if (!modulo) return;
    const dati = { nome: modulo.nome, membri: modulo.membri };
    azione(async () => {
      if (modulo.id === null) await post("/team", dati);
      else await patch(`/team/${modulo.id}`, dati);
      setModulo(null);
    }, modulo.id === null ? `Team «${modulo.nome}» creato.` : `Team «${modulo.nome}» aggiornato.`);
  }

  function elimina(t: Team) {
    if (!confirm(`Eliminare il team «${t.nome}»? Gli utenti restano nel CRM.`)) return;
    azione(() => cancella(`/team/${t.id}`), `Team «${t.nome}» eliminato.`);
  }

  return (
    <>
      <div className="testata">
        <h1>Team</h1>
        {!modulo && <button className="primario" onClick={() => apri(null)}>Nuovo team</button>}
      </div>
      <p className="tenue">
        Ogni campagna si assegna a un team: i suoi operatori si dividono i contatti prendendoli dalla coda. Una persona
        può stare in più team.
      </p>
      {errore && <div className="errore">{errore}</div>}
      {avviso && <div className="messaggio-ok">{avviso}</div>}

      {modulo && (
        <form className="scheda" onSubmit={salva}>
          <h3>{modulo.id === null ? "Nuovo team" : "Modifica team"}</h3>
          <div className="filtri">
            <label className="largo">
              Nome del team
              <input required autoFocus value={modulo.nome} onChange={(e) => setModulo({ ...modulo, nome: e.target.value })} placeholder="Officina Viterbo" />
            </label>
          </div>
          <DueElenchi
            voci={persone.map((p) => ({ id: p.id, nome: p.nome, nota: p.ruolo !== "operatore" ? RUOLI[p.ruolo] : undefined }))}
            scelti={modulo.membri}
            onCambia={(membri) => setModulo({ ...modulo, membri })}
            titoloDisponibili="Utenti disponibili"
            titoloScelti="Nel team"
          />
          <p className="tenue">Clicca i nomi per selezionarli e usa le frecce; con il doppio clic un nome passa subito dall'altra parte.</p>
          <div className="azioni">
            <button type="button" onClick={() => setModulo(null)}>Annulla</button>
            <button type="submit" className="primario">{modulo.id === null ? "Crea team" : "Salva"}</button>
          </div>
        </form>
      )}

      <table>
        <thead>
          <tr><th>Team</th><th>Persone</th><th className="num">Campagne</th><th>Stato</th><th></th></tr>
        </thead>
        <tbody>
          {team.map((t) => (
            <tr key={t.id} className={t.attivo ? "" : "spento"}>
              <td><strong>{t.nome}</strong></td>
              <td>
                {t.membri.length === 0 ? <span className="tenue">Nessuno</span> : (
                  <div className="etichette">{t.membri.map((m) => <span key={m.id}>{m.nome}</span>)}</div>
                )}
              </td>
              <td className="num">{t.campagne}</td>
              <td>{t.attivo ? "Attivo" : "Disattivato"}</td>
              <td>
                <div className="azioni-riga">
                  <button onClick={() => apri(t)}>Modifica</button>
                  <button onClick={() => azione(() => patch(`/team/${t.id}`, { attivo: !t.attivo }))}>
                    {t.attivo ? "Disattiva" : "Riattiva"}
                  </button>
                  <button
                    className="pericolo"
                    disabled={t.campagne > 0}
                    title={t.campagne > 0 ? "Ha delle campagne: si può solo disattivare" : ""}
                    onClick={() => elimina(t)}
                  >
                    Elimina
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {team.length === 0 && <tr><td colSpan={5} className="vuoto">Non ci sono ancora team: creane uno con «Nuovo team»</td></tr>}
        </tbody>
      </table>
    </>
  );
}
