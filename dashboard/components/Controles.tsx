"use client";

import type { Capa, ComunaResumen, Superficie, TipoDelito, Turno } from "@/lib/types";
import { CAPAS, SUPERFICIES, TIPOS, TURNOS } from "@/lib/types";
import { num } from "@/lib/formato";

/* Los filtros van todos arriba y siempre visibles: en un tablero, esconder un
   filtro activo detrás de un menú es la forma más rápida de que alguien lea mal
   un número. Cada control dice qué está aplicado sin tener que abrirlo. */

const CHIP =
  "px-2.5 py-1.5 text-xs font-medium rounded transition-colors duration-150 cursor-pointer " +
  "border disabled:cursor-not-allowed";

export function SelectorTurno({ valor, onChange }: { valor: Turno; onChange: (t: Turno) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">Turno</span>
      <div className="flex gap-1 p-0.5 bg-surface-sunk rounded" role="radiogroup" aria-label="Turno">
        {TURNOS.map((t) => {
          const activo = t.key === valor;
          return (
            <button
              key={t.key}
              role="radio"
              aria-checked={activo}
              onClick={() => onChange(t.key)}
              className={`${CHIP} border-transparent ${
                activo
                  ? "bg-brand text-white shadow-sm"
                  : "text-ink-2 hover:bg-surface-2 hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function SelectorComuna({
  valor, onChange, comunas,
}: { valor: number | null; onChange: (c: number | null) => void; comunas: ComunaResumen[] }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="f-comuna" className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
        Comuna
      </label>
      <select
        id="f-comuna"
        value={valor ?? ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
        className="h-[34px] px-2 text-xs bg-surface-2 border border-line rounded text-ink cursor-pointer
                   hover:border-line-strong transition-colors duration-150 min-w-[9.5rem]"
      >
        <option value="">Todas ({comunas.length})</option>
        {comunas.map((c) => (
          <option key={c.comuna} value={c.comuna}>
            Comuna {c.comuna} — {num(c.delitos_2025)} delitos
          </option>
        ))}
      </select>
    </div>
  );
}

/* Los dos tipos sin superficie de riesgo van en un optgroup aparte y con el
   texto "(sin superficie)" en la opción. Si estuvieran mezclados con el resto,
   elegir Vialidad y ver el mapa quieto se leería como un bug del tablero. */
export function SelectorTipo({
  valor, onChange,
}: { valor: TipoDelito; onChange: (t: TipoDelito) => void }) {
  const conSuperficie = TIPOS.filter((t) => t.superficie && t.key !== "todos");
  const sinSuperficie = TIPOS.filter((t) => !t.superficie);
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="f-tipo" className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
        Tipo de delito
      </label>
      <select
        id="f-tipo"
        value={valor}
        onChange={(e) => onChange(e.target.value as TipoDelito)}
        className="h-[34px] px-2 text-xs bg-surface-2 border border-line rounded text-ink cursor-pointer
                   hover:border-line-strong transition-colors duration-150 min-w-[10.5rem]"
      >
        <option value="todos">Todos los tipos</option>
        <optgroup label="Con superficie de riesgo propia">
          {conSuperficie.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </optgroup>
        <optgroup label="Solo delitos registrados">
          {sinSuperficie.map((t) => (
            <option key={t.key} value={t.key}>{t.label} (sin superficie)</option>
          ))}
        </optgroup>
      </select>
    </div>
  );
}

export function SelectorCapa({ valor, onChange }: { valor: Capa; onChange: (c: Capa) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="f-capa" className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
        Capa operativa
      </label>
      <select
        id="f-capa"
        value={valor}
        onChange={(e) => onChange(e.target.value as Capa)}
        className="h-[34px] px-2 text-xs bg-surface-2 border border-line rounded text-ink cursor-pointer
                   hover:border-line-strong transition-colors duration-150 min-w-[13rem]"
      >
        {CAPAS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
      </select>
    </div>
  );
}

export function ControlK({
  valor, onChange, disponibles,
}: { valor: number; onChange: (k: number) => void; disponibles: number[] }) {
  const idx = Math.max(0, disponibles.indexOf(valor));
  return (
    <div className="flex flex-col gap-1 min-w-[11rem]">
      <label htmlFor="f-k" className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
        Patrullas desplegadas: <span className="tabular text-ink font-semibold">{valor}</span>
      </label>
      <input
        id="f-k"
        type="range"
        min={0}
        max={disponibles.length - 1}
        step={1}
        value={idx}
        onChange={(e) => onChange(disponibles[Number(e.target.value)])}
        className="h-[34px] w-full cursor-pointer accent-[var(--brand)]"
        aria-valuetext={`${valor} patrullas`}
      />
    </div>
  );
}

export function ToggleTema({ tema, onChange }: { tema: "light" | "dark"; onChange: () => void }) {
  return (
    <button
      onClick={onChange}
      aria-label={`Cambiar a tema ${tema === "light" ? "oscuro" : "claro"}`}
      title={`Cambiar a tema ${tema === "light" ? "oscuro" : "claro"}`}
      className="h-[34px] w-[34px] grid place-items-center rounded border border-line bg-surface-2
                 text-ink-2 hover:text-ink hover:border-line-strong transition-colors duration-150 cursor-pointer"
    >
      {tema === "light" ? (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
        </svg>
      ) : (
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
             strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
        </svg>
      )}
    </button>
  );
}

function Chip({ texto, onQuitar }: { texto: string; onQuitar: () => void }) {
  return (
    <button
      onClick={onQuitar}
      className="inline-flex items-center gap-1.5 px-2 py-1 text-[11px] rounded-full cursor-pointer
                 bg-[var(--brand-wash)] text-brand border border-transparent
                 hover:border-brand transition-colors duration-150"
    >
      {texto}
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           strokeWidth="3" strokeLinecap="round" aria-hidden="true">
        <path d="M18 6 6 18M6 6l12 12" />
      </svg>
      <span className="sr-only">Quitar filtro</span>
    </button>
  );
}

/** Muestra los filtros activos y permite limpiarlos de a uno. Sin esto, alguien
 *  que vuelve al tablero después de un rato no sabe qué está viendo. */
export function ChipsActivos({
  comuna, barrio, tipo, onLimpiarComuna, onLimpiarBarrio, onLimpiarTipo,
}: {
  comuna: number | null; barrio: string | null; tipo: TipoDelito;
  onLimpiarComuna: () => void; onLimpiarBarrio: () => void; onLimpiarTipo: () => void;
}) {
  if (comuna === null && !barrio && tipo === "todos") return null;
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {tipo !== "todos" && (
        <Chip texto={TIPOS.find((t) => t.key === tipo)!.label} onQuitar={onLimpiarTipo} />
      )}
      {comuna !== null && <Chip texto={`Comuna ${comuna}`} onQuitar={onLimpiarComuna} />}
      {barrio && <Chip texto={barrio} onQuitar={onLimpiarBarrio} />}
    </div>
  );
}


/* Qué superficie pinta el mapa. Va en un select y no en chips porque comparte
   fila con los otros filtros y tres chips de texto largo la desbordan.

   La opción demográfica lleva "(por comuna)" en la etiqueta por la misma razón
   por la que los tipos sin superficie de riesgo llevan "(sin superficie)": al
   elegirla cambia la geometría del mapa —15 polígonos en vez de 48— y sin
   avisarlo eso se lee como que el mapa se rompió. */
export function SelectorSuperficie({
  valor, onChange,
}: { valor: Superficie; onChange: (s: Superficie) => void }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor="f-superficie" className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
        Qué pinta el mapa
      </label>
      <select
        id="f-superficie"
        value={valor}
        onChange={(e) => onChange(e.target.value as Superficie)}
        className="h-[34px] px-2 text-xs bg-surface-2 border border-line rounded text-ink cursor-pointer
                   hover:border-line-strong transition-colors duration-150 min-w-[11rem]"
      >
        {SUPERFICIES.map((s) => (
          <option key={s.key} value={s.key}>
            {s.label}{s.unidad === "comuna" ? " (por comuna)" : ""}
          </option>
        ))}
      </select>
    </div>
  );
}
