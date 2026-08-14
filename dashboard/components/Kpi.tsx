"use client";

import type { ReactNode } from "react";

type Tono = "neutro" | "bueno" | "alerta" | "malo";

const TONO: Record<Tono, string> = {
  neutro: "text-ink-2",
  bueno: "text-[var(--good)]",
  alerta: "text-[var(--warn)]",
  malo: "text-[var(--bad)]",
};

export interface KpiProps {
  etiqueta: string;
  valor: string;
  unidad?: string;
  nota?: ReactNode;
  delta?: { texto: string; tono: Tono };
  /** Serie chica para el sparkline. Se dibuja solo si tiene 3+ puntos. */
  chispa?: number[];
  /** Explica de dónde sale el número; aparece al pasar el cursor. */
  ayuda?: string;
}

function Sparkline({ datos }: { datos: number[] }) {
  if (datos.length < 3) return null;
  const min = Math.min(...datos);
  const max = Math.max(...datos);
  const rango = max - min || 1;
  const w = 96, h = 26;
  const pts = datos.map((v, i) => [
    (i / (datos.length - 1)) * w,
    h - ((v - min) / rango) * (h - 4) - 2,
  ]);
  const d = "M" + pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L");
  const [ux, uy] = pts[pts.length - 1];
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} className="shrink-0" aria-hidden="true">
      <path d={`${d} L${w},${h} L0,${h} Z`} fill="var(--brand-wash)" />
      <path d={d} fill="none" stroke="var(--brand)" strokeWidth="1.5"
            strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={ux} cy={uy} r="2.5" fill="var(--brand)" />
    </svg>
  );
}

export function KpiCard({ etiqueta, valor, unidad, nota, delta, chispa, ayuda }: KpiProps) {
  return (
    <div className="card px-3.5 py-3 flex flex-col gap-1.5 min-w-0" title={ayuda}>
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.07em] text-ink-muted leading-tight">
          {etiqueta}
        </span>
        {delta && (
          <span className={`text-[11px] font-semibold tabular shrink-0 ${TONO[delta.tono]}`}>
            {delta.texto}
          </span>
        )}
      </div>
      <div className="flex items-end justify-between gap-2">
        <div className="flex items-baseline gap-1 min-w-0">
          <span className="text-[26px] leading-none font-semibold tabular truncate">{valor}</span>
          {unidad && <span className="text-sm text-ink-muted shrink-0">{unidad}</span>}
        </div>
        {chispa && <Sparkline datos={chispa} />}
      </div>
      {nota && <div className="text-[11.5px] text-ink-muted leading-snug">{nota}</div>}
    </div>
  );
}

export function KpiRow({ items }: { items: KpiProps[] }) {
  return (
    <div className="grid gap-2 grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
      {items.map((k) => <KpiCard key={k.etiqueta} {...k} />)}
    </div>
  );
}
