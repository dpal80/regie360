import { useEffect, useState, type FormEvent } from "react";
import { api, patch, post } from "../api";

type Membro = { id: number; nome: string; ruolo: string; attivo: boolean };
type Team = { id: number; nome: string; attivo: boolean; membri: Membro[] };

export default function TeamPagina() {
  const [team, setTeam] = useState<Team[]>([]);
  const [utenti, setUtenti] = useState<Membro[]>([]);
  const [nome, setNome] = useState("");
  const [errore, setErrore] = useState("");

  const carica = () => api<Team[]>("/team").then(setTeam).catch((e) => setErrore(e.message));
  useEffect(() => {
    carica();
    api<Membro[]>("/utenti").then((u) => setUtenti(u.filter((x) => x.attivo))).catch(() => undefined);
  }, []);

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
      await post("/team", { nome, membri: [] });
      setNome("");
    });
  }

  function cambiaMembro(t: Team, utenteId: number, dentro: boolean) {
    const membri = t.membri.map((m) => m.id).filter((id) => id !== utenteId);
    if (dentro) membri.push(utenteId);
    azione(() => patch(`/team/${t.id}`, { membri }));
  }

  return (
    <>
      <h1>Team</h1>
      <p className="tenue">
        Ogni campagna si assegna a un team: i suoi operatori si dividono i contatti prendendoli dalla coda. Una persona
        può stare in più team.
      </p>
      {errore && <div className="errore">{errore}</div>}
      <form className="filtri scheda" onSubmit={aggiungi}>
        <label>Nuovo team<input required value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Officina Viterbo" /></label>
        <div className="azioni"><button className="primario" type="submit">Crea team</button></div>
      </form>
      {team.length === 0 && <p className="tenue">Non ci sono ancora team.</p>}
      {team.map((t) => (
        <section key={t.id} className={`scheda ${t.attivo ? "" : "spenta"}`}>
          <div className="testata">
            <h3>{t.nome} {!t.attivo && <small className="tenue">(disattivato)</small>}</h3>
            <button onClick={() => azione(() => patch(`/team/${t.id}`, { attivo: !t.attivo }))}>
              {t.attivo ? "Disattiva" : "Riattiva"}
            </button>
          </div>
          <div className="spunte">
            {utenti.map((u) => (
              <label key={u.id} className="spunta">
                <input
                  type="checkbox"
                  checked={t.membri.some((m) => m.id === u.id)}
                  onChange={(e) => cambiaMembro(t, u.id, e.target.checked)}
                />
                {u.nome} {u.ruolo === "responsabile" && <small className="tenue">(Responsabile)</small>}
              </label>
            ))}
          </div>
        </section>
      ))}
    </>
  );
}
