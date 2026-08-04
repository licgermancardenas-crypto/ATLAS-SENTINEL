"use client";

import { useState } from "react";
import type { EvolucionMes } from "@/lib/types";

interface Props {
  datos: EvolucionMes[];
}

const W = 280;
const H = 160;
const PAD_L = 34;
const PAD_B = 20;
const PAD_T = 12;
const PAD_R = 8;

export default function EvolucionChart({ datos }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const valores = datos.map((d) => d.recall_20pct);
  const min = Math.min(...valores) * 0.95;
  const max = Math.max(...valores) * 1.05;

  const escalaX = (i: number) => PAD_L + (i / (datos.length - 1)) * (W - PAD_L - PAD_R);
  const escalaY = (v: number) => H - PAD_B - ((v - min) / (max - min)) * (H - PAD_B - PAD_T);

  const puntos = datos.map((d, i) => `${escalaX(i)},${escalaY(d.recall_20pct)}`).join(" ");

  return (
    <div>
      <svg width={W} height={H} role="img" aria-label="Recall@20% mes a mes, test 2025">
        <line x1={PAD_L} y1={H - PAD_B} x2={W - PAD_R} y2={H - PAD_B} stroke="var(--border)" strokeWidth={1} />
        <text x={4} y={escalaY(max) + 3} fontSize={9} fill="var(--text-secondary)">{(max * 100).toFixed(0)}%</text>
        <text x={4} y={escalaY(min) + 3} fontSize={9} fill="var(--text-secondary)">{(min * 100).toFixed(0)}%</text>

        <polyline points={puntos} fill="none" stroke="var(--risk-400)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
        {datos.map((d, i) => (
          <circle
            key={d.mes}
            cx={escalaX(i)}
            cy={escalaY(d.recall_20pct)}
            r={hover === i ? 5 : 3}
            fill="var(--risk-400)"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            style={{ cursor: "pointer" }}
          />
        ))}
      </svg>
      <div className="h-5 text-xs font-mono text-text-secondary">
        {hover !== null
          ? `${datos[hover].mes}: Recall@20% ${(datos[hover].recall_20pct * 100).toFixed(1)}%`
          : `Recall@20% estable: ${(Math.min(...valores) * 100).toFixed(0)}%–${(Math.max(...valores) * 100).toFixed(0)}% los 12 meses`}
      </div>
    </div>
  );
}
