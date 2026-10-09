import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { eResponsabile, eSuperadmin, RUOLI } from "./api";
import { useAuth } from "./auth";
import Login from "./pages/Login";
import Home from "./pages/Home";
import Clienti from "./pages/Clienti";
import ClienteDettaglio from "./pages/ClienteDettaglio";
import Veicoli from "./pages/Veicoli";
import Importa from "./pages/Importa";
import Utenti from "./pages/Utenti";
import Registro from "./pages/Registro";
import CambioPassword from "./pages/CambioPassword";
import Chiamate from "./pages/Chiamate";
import Contatto from "./pages/Contatto";
import Opportunita from "./pages/Opportunita";
import Campagne from "./pages/Campagne";
import CampagnaDettaglio from "./pages/CampagnaDettaglio";
import Team from "./pages/Team";
import Elenchi from "./pages/Elenchi";
import ActiveDirectory from "./pages/ActiveDirectory";
import Telefono from "./pages/Telefono";
import Microsoft365 from "./pages/Microsoft365";
import { TelefonoProvider } from "./telefono";

export default function App() {
  const { utente, caricamento, logout } = useAuth();

  if (caricamento) return <div className="centro">Caricamento…</div>;
  if (!utente) return <Login />;
  if (utente.deve_cambiare_password) {
    return (
      <div className="login">
        <CambioPassword obbligatorio />
      </div>
    );
  }

  const responsabile = eResponsabile(utente);
  const superadmin = eSuperadmin(utente);

  return (
    <TelefonoProvider>
    <div className="layout">
      <aside className="menu">
        <div className="logo">
          <img src="/logo-bianco.svg" alt="Regie360" />
        </div>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          <NavLink to="/chiamate">Le mie chiamate</NavLink>
          <NavLink to="/opportunita">Opportunità</NavLink>
          <NavLink to="/telefono">Telefono</NavLink>
          {responsabile && (
            <>
              <NavLink to="/campagne">Campagne</NavLink>
              <NavLink to="/team">Team</NavLink>
              <NavLink to="/clienti">Clienti</NavLink>
              <NavLink to="/veicoli">Veicoli</NavLink>
              <NavLink to="/importa">Importa dati</NavLink>
              <NavLink to="/utenti">Utenti</NavLink>
              <NavLink to="/elenchi">Elenchi</NavLink>
              {superadmin && <NavLink to="/active-directory">Active Directory</NavLink>}
              {superadmin && <NavLink to="/microsoft365">Microsoft 365</NavLink>}
              <NavLink to="/registro">Registro attività</NavLink>
            </>
          )}
        </nav>
        <div className="chi">
          <div>{utente.nome}</div>
          <small>{RUOLI[utente.ruolo]}</small>
          {utente.origine === "locale" && <NavLink to="/password" className="link-chiaro">Cambia password</NavLink>}
          <button className="link" onClick={logout}>Esci</button>
        </div>
      </aside>
      <main className="contenuto">
        <Routes>
          <Route path="/" element={<Home />} />
          {utente.origine === "locale" && <Route path="/password" element={<CambioPassword />} />}
          <Route path="/chiamate" element={<Chiamate />} />
          <Route path="/contatti/:id" element={<Contatto />} />
          <Route path="/opportunita" element={<Opportunita />} />
          <Route path="/telefono" element={<Telefono />} />
          {responsabile && (
            <>
              <Route path="/campagne" element={<Campagne />} />
              <Route path="/campagne/:id" element={<CampagnaDettaglio />} />
              <Route path="/team" element={<Team />} />
              <Route path="/elenchi" element={<Elenchi />} />
              {superadmin && <Route path="/active-directory" element={<ActiveDirectory />} />}
              {superadmin && <Route path="/microsoft365" element={<Microsoft365 />} />}
              <Route path="/clienti" element={<Clienti />} />
              <Route path="/clienti/:id" element={<ClienteDettaglio />} />
              <Route path="/veicoli" element={<Veicoli />} />
              <Route path="/importa" element={<Importa />} />
              <Route path="/utenti" element={<Utenti />} />
              <Route path="/registro" element={<Registro />} />
            </>
          )}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
    </TelefonoProvider>
  );
}
