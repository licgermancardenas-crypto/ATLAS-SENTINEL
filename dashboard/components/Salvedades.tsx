"use client";

import { useState } from "react";

/* Las salvedades van en el tablero, no en un anexo. Un tablero que muestra
   números sin decir de qué no responden invita a leerlos como si respondieran
   de todo. Arranca colapsado para no competir con los datos, pero el título
   dice el número: no se puede pasar de largo sin verlo. */

export default function Salvedades({ items }: { items: string[] }) {
  const [abierto, setAbierto] = useState(false);
  return (
    <section className="card overflow-hidden">
      <button
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="w-full px-3 py-2.5 flex items-center gap-2 cursor-pointer text-left
                   hover:bg-surface-sunk transition-colors duration-150"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--warn)"
             strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
             className="shrink-0" aria-hidden="true">
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <path d="M12 9v4M12 17h.01" />
        </svg>
        <span className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 flex-1">
          Qué no dicen estos números
        </span>
        <span className="text-[11px] text-ink-muted tabular">{items.length}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
             className={`shrink-0 text-ink-muted transition-transform duration-200 ${abierto ? "rotate-180" : ""}`}
             aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {abierto && (
        <ul className="px-3 pb-3 flex flex-col gap-2.5 border-t border-line pt-2.5">
          {items.map((s, i) => (
            <li key={i} className="text-[11.5px] leading-relaxed text-ink-2 flex gap-2">
              <span className="text-ink-muted tabular shrink-0">{i + 1}.</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
