"use client";

import { useMemo, useState } from "react";
import type { BarrioProps, Turno } from "@/lib/types";
import { claveRiesgo } from "@/lib/types";
import { num, num3 } from "@/lib/formato";
import { claseDe, cortesPorCuantil, ETIQUETAS_CLASE, VAR_RIESGO } from "@/lib/escala";

type Columna = "nombre" | "comuna" | "riesgo" | "delitos_2025" | "n_hex";

const COLUMNAS: { key: Columna; label: string; numerica: boolean }[] = [
  { key: "nombre", label: "Barrio", numerica: false },
  { key: "comuna", label: "Comuna", numerica: true },
  { key: "riesgo", label: "Riesgo", numerica: true },
  { key: "delitos_2025", label: "Delitos 2025", numerica: true },
  { key: "n_hex", label: "Celdas", numerica: true },
];

export default function TablaBarrios({
  barrios, turno, comuna, barrioActivo, onBarrio,
}: {
  barrios: BarrioProps[]; turno: Turno; comuna: number | null;
  barrioActivo: string | null; onBarrio: (n: string | null) => void;
}) {
  const [orden, setOrden] = useState<{ col: Columna; desc: boolean }>({ col: "riesgo", desc: true });
  const clave = claveRiesgo(turno);

  const cortes = useMemo(
    () => cortesPorCuantil(barrios.map((b) => b[clave] as number)),
    [barrios, clave],
  );

  const filas = useMemo(() => {
    const base = comuna === null ? barrios : barrios.filter((b) => b.comuna === comuna);
    const valor = (b: BarrioProps) =>
      orden.col === "riesgo" ? (b[clave] as number) : (b[orden.col] as string | number);
    return [...base].sort((a, b) => {
      const va = valor(a), vb = valor(b);
      const cmp = typeof va === "string" ? va.localeCompare(vb as string, "es") : (va as number) - (vb as number);
      return orden.desc ? -cmp : cmp;
    });
  }, [barrios, comuna, orden, clave]);

  const alternar = (col: Columna) =>
    setOrden((o) => (o.col === col ? { col, desc: !o.desc } : { col, desc: col !== "nombre" }));

  return (
    <div className="flex flex-col min-h-0">
      <div className="flex items-baseline justify-between px-3 py-2 border-b border-line shrink-0">
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Detalle por barrio
        </h2>
        <span className="text-[11px] text-ink-muted tabular">
          {num(filas.length)} de {num(barrios.length)}
        </span>
      </div>

      <div className="overflow-auto scroll-fino min-h-0">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-surface-2 z-10">
            <tr>
              {COLUMNAS.map((c) => {
                const activa = orden.col === c.key;
                return (
                  <th
                    key={c.key}
                    scope="col"
                    aria-sort={activa ? (orden.desc ? "descending" : "ascending") : "none"}
                    className={`border-b border-line px-3 py-2 font-medium text-[10.5px] uppercase
                                tracking-[0.06em] whitespace-nowrap ${c.numerica ? "text-right" : "text-left"}`}
                  >
                    <button
                      onClick={() => alternar(c.key)}
                      className={`inline-flex items-center gap-1 cursor-pointer transition-colors duration-150
                                  ${activa ? "text-brand" : "text-ink-muted hover:text-ink-2"}`}
                    >
                      {c.label}
                      <span aria-hidden="true" className={activa ? "opacity-100" : "opacity-25"}>
                        {activa && !orden.desc ? "▲" : "▼"}
                      </span>
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {filas.map((b) => {
              const v = b[clave] as number;
              const cl = claseDe(v, cortes);
              const activo = barrioActivo === b.nombre;
              return (
                <tr
                  key={b.nombre}
                  onClick={() => onBarrio(activo ? null : b.nombre)}
                  className={`cursor-pointer transition-colors duration-150 ${
                    activo ? "bg-[var(--brand-wash)]" : "hover:bg-surface-sunk"
                  }`}
                >
                  <td className="border-b border-line px-3 py-1.5 whitespace-nowrap">
                    <span className="inline-flex items-center gap-2">
                      {/* el cuadrito repite la clase que muestra el mapa: el color
                          no es el único portador, al lado va el número */}
                      <span
                        className="w-2.5 h-2.5 rounded-[2px] shrink-0"
                        style={{ background: `var(${VAR_RIESGO[cl]})` }}
                        title={ETIQUETAS_CLASE[cl]}
                      />
                      <span className={activo ? "font-semibold text-brand" : ""}>{b.nombre}</span>
                    </span>
                  </td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-2">{b.comuna ?? "—"}</td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular font-medium">{num3(v)}</td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-2">{num(b.delitos_2025)}</td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-muted">{b.n_hex}</td>
                </tr>
              );
            })}
            {filas.length === 0 && (
              <tr>
                <td colSpan={COLUMNAS.length} className="px-3 py-8 text-center text-ink-muted">
                  No hay barrios para este filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
