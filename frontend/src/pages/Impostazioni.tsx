import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import ActiveDirectory from "./ActiveDirectory";
import Microsoft365 from "./Microsoft365";
import NethVoice from "./NethVoice";

// I collegamenti del CRM ai sistemi dell'azienda, tutti in un posto: una scheda per ciascuno.
const SCHEDE = [
  { percorso: "active-directory", titolo: "Active Directory", pagina: <ActiveDirectory /> },
  { percorso: "microsoft365", titolo: "Microsoft 365", pagina: <Microsoft365 /> },
  { percorso: "nethvoice", titolo: "NethVoice", pagina: <NethVoice /> },
];

export default function Impostazioni() {
  return (
    <>
      <h1>Impostazioni</h1>
      <nav className="schede-menu">
        {SCHEDE.map((s) => <NavLink key={s.percorso} to={`/impostazioni/${s.percorso}`} className="scheda-voce">{s.titolo}</NavLink>)}
      </nav>
      <Routes>
        {SCHEDE.map((s) => <Route key={s.percorso} path={s.percorso} element={s.pagina} />)}
        <Route path="*" element={<Navigate to={`/impostazioni/${SCHEDE[0].percorso}`} replace />} />
      </Routes>
    </>
  );
}
