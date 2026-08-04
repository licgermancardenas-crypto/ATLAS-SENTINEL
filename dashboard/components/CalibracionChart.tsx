"use client";

import { useState } from "react";
import type { CalibracionDecil } from "@/lib/types";

interface Props {
  datos: CalibracionDecil[];
}

const W = 280;
const H = 220;
const PAD = 32;

export default function CalibracionChart({ datos }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...datos.map((d) => Math.max(d.pred_medio, d.real_medio))) * 1.08;

  const escalaX = (v: number) => PAD + (v / max) * (W - PAD - 12);
  const escalaY = (v: number) => H - PAD - (v / max) * (H - PAD - 12);

  return (
    <div>
      <svg width={W} height={H} role="img" aria-label="Calibración: riesgo predicho vs. real por decil">
        {/* diagonal ideal */}
        <line x1={escalaX(0)} y1={escalaY(0)} x2={escalaX(max)} y2={escalaY(max)} stroke="var(--border)" strokeWidth={1.5} strokeDasharray="3 3" />
        {/* ejes */}
        <line x1={PAD} y1={H - PAD} x2={W - 12} y2={H - PAD} stroke="var(--border)" strokeWidth={1} />
        <line x1={PAD} y1={12} x2={PAD} y2={H - PAD} stroke="var(--border)" strokeWidth={1} />
        <text x={W / 2} y={H - 6} textAnchor="middle" fontSize={10} fill="var(--text-secondary)">predicho</text>
        <text x={10} y={H / 2} textAnchor="middle" fontSize={10} fill="var(--text-secondary)" transform={`rotate(-90 10 ${H / 2})`}>real</text>

        {/* puntos: pred vs real por decil */}
        {datos.map((d) => (
          <circle
            key={d.decil}
            cx={escalaX(d.pred_medio)}
            cy={escalaY(d.real_medio)}
            r={hover === d.decil ? 6 : 4}
            fill="var(--risk-400)"
            stroke="var(--surface-2)"
            strokeWidth={1.5}
            onMouseEnter={() => setHover(d.decil)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "pointer", transition: "r 120ms ease-out" }}
          />
        ))}
      </svg>
      <div className="h-5 text-xs font-mono text-text-secondary">
        {hover !== null && (() => {
          const d = datos.find((x) => x.decil === hover)!;
          return `decil ${d.decil}: predicho ${d.pred_medio.toFixed(3)} · real ${d.real_medio.toFixed(3)}`;
        })()}
      </div>
    </div>
  );
}
