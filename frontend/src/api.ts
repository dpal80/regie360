// Tutte le chiamate al backend passano da qui: cookie di sessione e intestazione anti-CSRF.

export class ErroreApi extends Error {
  constructor(
    public stato: number,
    messaggio: string,
    public dettagli?: unknown,
  ) {
    super(messaggio);
  }
}

function messaggioDa(detail: unknown, stato: number): string {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "errori" in detail) {
    return (detail as { errori: string[] }).errori.join("\n");
  }
  if (Array.isArray(detail)) return "Dati non validi";
  return stato >= 500 ? "Errore del server, riprova" : "Richiesta non riuscita";
}

export async function api<T>(percorso: string, opzioni: RequestInit = {}): Promise<T> {
  const headers = new Headers(opzioni.headers);
  headers.set("X-Requested-With", "crm");
  if (opzioni.body && !(opzioni.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const r = await fetch(`/api${percorso}`, { ...opzioni, headers, credentials: "same-origin" });
  if (r.status === 401 && percorso !== "/auth/login" && percorso !== "/auth/me") {
    window.dispatchEvent(new Event("sessione-scaduta"));
  }
  if (r.status === 204) return undefined as T;
  const corpo = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = corpo?.detail;
    throw new ErroreApi(r.status, messaggioDa(detail, r.status), detail);
  }
  return corpo as T;
}

export const post = <T>(percorso: string, dati?: unknown) =>
  api<T>(percorso, { method: "POST", body: dati === undefined ? undefined : JSON.stringify(dati) });

export const patch = <T>(percorso: string, dati: unknown) =>
  api<T>(percorso, { method: "PATCH", body: JSON.stringify(dati) });

export function query(parametri: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(parametri)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function formatoData(d: string | null | undefined): string {
  if (!d) return "";
  const [a, m, g] = d.slice(0, 10).split("-");
  return `${g}/${m}/${a}`;
}

export function formatoDataOra(d: string | null | undefined): string {
  if (!d) return "";
  return new Date(d).toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
}

export type Utente = {
  id: number;
  username: string;
  nome: string;
  ruolo: "responsabile" | "operatore";
  origine: "ad" | "locale";
  interno: string | null;
};

export type Pagina<T> = { totale: number; pagina: number; per_pagina: number; elementi: T[] };
