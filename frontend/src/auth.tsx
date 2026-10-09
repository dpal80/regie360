import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, post, type Utente } from "./api";

type Auth = {
  utente: Utente | null;
  caricamento: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  ricarica: () => Promise<void>;
};

const Contesto = createContext<Auth | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [utente, setUtente] = useState<Utente | null>(null);
  const [caricamento, setCaricamento] = useState(true);

  useEffect(() => {
    api<Utente>("/auth/me")
      .then(setUtente)
      .catch(() => setUtente(null))
      .finally(() => setCaricamento(false));
    const scaduta = () => setUtente(null);
    window.addEventListener("sessione-scaduta", scaduta);
    return () => window.removeEventListener("sessione-scaduta", scaduta);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    setUtente(await post<Utente>("/auth/login", { username, password }));
  }, []);

  const logout = useCallback(async () => {
    await post("/auth/logout").catch(() => undefined);
    setUtente(null);
  }, []);

  const ricarica = useCallback(async () => {
    setUtente(await api<Utente>("/auth/me"));
  }, []);

  return <Contesto.Provider value={{ utente, caricamento, login, logout, ricarica }}>{children}</Contesto.Provider>;
}

export function useAuth(): Auth {
  const c = useContext(Contesto);
  if (!c) throw new Error("useAuth fuori da AuthProvider");
  return c;
}
