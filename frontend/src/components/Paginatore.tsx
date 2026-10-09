type Props = { pagina: number; perPagina: number; totale: number; onCambia: (p: number) => void };

export default function Paginatore({ pagina, perPagina, totale, onCambia }: Props) {
  const pagine = Math.max(1, Math.ceil(totale / perPagina));
  return (
    <div className="paginatore">
      <span>
        {totale.toLocaleString("it-IT")} risultati · pagina {pagina} di {pagine}
      </span>
      <button disabled={pagina <= 1} onClick={() => onCambia(pagina - 1)}>‹ Precedente</button>
      <button disabled={pagina >= pagine} onClick={() => onCambia(pagina + 1)}>Successiva ›</button>
    </div>
  );
}
