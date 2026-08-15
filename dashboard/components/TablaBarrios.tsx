"use client";

import { useMemo, useState } from "react";
import type { BarrioProps, TipoDelito, Turno } from "@/lib/types";
import { claveDelitos, claveRiesgo, riesgoEsDelTipo, tasaInflada, tipoInfo } from "@/lib/types";
import { num, num3, tasa100k } from "@/lib/formato";
import { claseDe, cortesPorCuantil, ETIQUETAS_CLASE, VAR_RIESGO } from "@/lib/escala";

type Columna = "nombre" | "comuna" | "riesgo" | "delitos" | "tasa" | "n_hex";

/* La tasa cada 100.000 divide por población residente, así que en los barrios
   donde entra mucha gente que no vive ahí queda inflada. El asterisco marca el
   quinto superior de afluencia no residente (subte + tren + EcoBici por
   habitante). No corrige el número — avisa que compara peor que los otros.

   La ausencia de asterisco NO garantiza lo contrario: falta el colectivo, del
   que no hay pasajeros por parada publicados. Está medido contra la ENMODO
   2018 en src/validation/validar_presion_visitantes.py — Spearman 0,77, y lo
   que queda sin cubrir es Mataderos, que recibe gente en bondi. */
function TasaCelda({ barrio, claveD }: { barrio: BarrioProps; claveD: string }) {
  const t = tasa100k(barrio[claveD] as number, barrio.poblacion as number);
  if (t === null) return <span className="text-ink-muted">—</span>;
  const inflada = tasaInflada(barrio.presion_visitantes as number | null);
  return (
    <span title={inflada
      ? `${barrio.nombre} está entre los barrios con más afluencia de gente que no vive ahí, `
        + "así que esta tasa —que divide por población residente— queda sobreestimada."
      : undefined}>
      {num(t)}
      {inflada && <span className="text-[var(--warn)] ml-0.5" aria-label="tasa sobreestimada">*</span>}
    </span>
  );
}

export default function TablaBarrios({
  barrios, turno, tipo, comuna, barrioActivo, onBarrio,
}: {
  barrios: BarrioProps[]; turno: Turno; tipo: TipoDelito; comuna: number | null;
  barrioActivo: string | null; onBarrio: (n: string | null) => void;
}) {
  const [orden, setOrden] = useState<{ col: Columna; desc: boolean }>({ col: "riesgo", desc: true });
  const clave = claveRiesgo(turno, tipo);
  const claveD = claveDelitos(tipo);

  // los encabezados dicen de qué tipo son las dos columnas que cambian; si
  // dijeran siempre "Riesgo" y "Delitos 2025", una tabla filtrada por hurto
  // sería indistinguible de una sin filtrar en una captura de pantalla
  const columnas: { key: Columna; label: string; numerica: boolean }[] = [
    { key: "nombre", label: "Barrio", numerica: false },
    { key: "comuna", label: "Comuna", numerica: true },
    { key: "riesgo", label: riesgoEsDelTipo(tipo) ? `Riesgo ${tipoInfo(tipo).label.toLowerCase()}`
                                                  : tipo === "todos" ? "Riesgo" : "Riesgo agregado",
      numerica: true },
    { key: "delitos", label: tipo === "todos" ? "Delitos 2025" : `${tipoInfo(tipo).label} 2025`,
      numerica: true },
    { key: "tasa", label: "Cada 100k", numerica: true },
    { key: "n_hex", label: "Celdas", numerica: true },
  ];

  const cortes = useMemo(
    () => cortesPorCuantil(barrios.map((b) => b[clave] as number)),
    [barrios, clave],
  );

  const filas = useMemo(() => {
    const base = comuna === null ? barrios : barrios.filter((b) => b.comuna === comuna);
    const campo = (c: Columna) => (c === "riesgo" ? clave : c === "delitos" ? claveD : c);
    const valor = (b: BarrioProps): string | number =>
      orden.col === "tasa"
        ? tasa100k(b[claveD] as number, b.poblacion as number) ?? -1
        : (b[campo(orden.col)] as string | number);
    return [...base].sort((a, b) => {
      const va = valor(a), vb = valor(b);
      const cmp = typeof va === "string" ? va.localeCompare(vb as string, "es") : (va as number) - (vb as number);
      return orden.desc ? -cmp : cmp;
    });
  }, [barrios, comuna, orden, clave, claveD]);

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
              {columnas.map((c) => {
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
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-2">{num(b[claveD] as number)}</td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-2">
                    <TasaCelda barrio={b} claveD={claveD} />
                  </td>
                  <td className="border-b border-line px-3 py-1.5 text-right tabular text-ink-muted">{b.n_hex}</td>
                </tr>
              );
            })}
            {filas.length === 0 && (
              <tr>
                <td colSpan={columnas.length} className="px-3 py-8 text-center text-ink-muted">
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
