import { Navigate, NavLink, Route, Routes } from "react-router-dom";
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

  const responsabile = utente.ruolo === "responsabile";

  return (
    <div className="layout">
      <aside className="menu">
        <div className="logo">
          <img src="/logo-bianco.svg" alt="Regie360" />
        </div>
        <nav>
          <NavLink to="/" end>Home</NavLink>
          {responsabile && (
            <>
              <NavLink to="/clienti">Clienti</NavLink>
              <NavLink to="/veicoli">Veicoli</NavLink>
              <NavLink to="/importa">Importa dati</NavLink>
              <NavLink to="/utenti">Utenti</NavLink>
              <NavLink to="/registro">Registro attività</NavLink>
            </>
          )}
        </nav>
        <div className="chi">
          <div>{utente.nome}</div>
          <small>{responsabile ? "Responsabile" : "Operatore"}</small>
          {utente.origine === "locale" && <NavLink to="/password" className="link-chiaro">Cambia password</NavLink>}
          <button className="link" onClick={logout}>Esci</button>
        </div>
      </aside>
      <main className="contenuto">
        <Routes>
          <Route path="/" element={<Home />} />
          {utente.origine === "locale" && <Route path="/password" element={<CambioPassword />} />}
          {responsabile && (
            <>
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
  );
}
