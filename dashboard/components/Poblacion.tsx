"use client";

import { useState } from "react";
import type { Demografia, DemoBarrio, DemoComuna } from "@/lib/types";
import { num, num1, pct } from "@/lib/formato";
import { KpiCard } from "./Kpi";

/* Quién vive en cada zona. Es el denominador de todo lo demás del tablero —la
   tasa cada 100.000 sale de acá— y hasta ahora existía solo por detrás, sin
   que se pudiera mirar.

   Tres decisiones que vienen de los datos y no del diseño:

   1. **La edad se muestra a nivel comuna incluso cuando hay un barrio
      elegido**, con la etiqueta diciéndolo. El Censo 2022 no está publicado
      por radio censal ni por barrio, así que la alternativa era no mostrar
      edad al elegir un barrio; mostrar la de su comuna informa más, siempre
      que quede claro de qué unidad es el número.
   2. **Los años van pegados a cada número, no en una nota general.** Población
      y sexo son 2010 y la edad es 2022, con 231.556 personas de diferencia
      entre los dos censos. Alguien que multiplique la población de 2010 por el
      17,4% de mayores de 2022 obtiene un número que no existe.
   3. **Densidad y "mujeres cada 100 varones" antes que los porcentajes
      crudos.** Un 54% de mujeres no se puede dimensionar; "117 mujeres cada
      100 varones" sí, y es además el índice que publica INDEC. */

type Vista = "poblacion" | "densidad";

export default function Poblacion({
  datos, comuna, barrio, onComuna, onBarrio,
}: {
  datos: Demografia;
  comuna: number | null;
  barrio: string | null;
  onComuna: (c: number | null) => void;
  onBarrio: (b: string | null) => void;
}) {
  const [vista, setVista] = useState<Vista>("poblacion");

  const b: DemoBarrio | undefined = barrio
    ? datos.barrios.find((x) => x.nombre === barrio) : undefined;
  /* la comuna del bloque de edad: la elegida, o la del barrio elegido. Cuando
     hay barrio pero no comuna en el estado, igual se resuelve — el tablero
     fija la comuna al elegir barrio, pero no conviene depender de eso acá */
  const nroComuna = comuna ?? b?.comuna ?? null;
  const c: DemoComuna | undefined = nroComuna != null
    ? datos.comunas.find((x) => x.comuna === nroComuna) : undefined;

  /* La unidad de la que hablan población, sexo y densidad. Se normaliza a una
     forma común en vez de usar la unión de los tres tipos: el bloque de Ciudad
     llama `total` a lo que barrio y comuna llaman `poblacion`, y arrastrar esa
     diferencia obliga a un condicional en cada uso. */
  const unidad = b ?? c ?? {
    poblacion: datos.poblacion.total,
    varones: datos.poblacion.varones,
    mujeres: datos.poblacion.mujeres,
    area_km2: datos.poblacion.area_km2 as number | null,
    densidad: datos.poblacion.densidad as number | null,
  };
  const ambito = b ? b.nombre : c ? `Comuna ${c.comuna}` : "toda la Ciudad";
  const share = unidad.poblacion / datos.poblacion.total;

  // la unidad de la que habla la edad, que puede no ser la misma
  const edad = c ?? datos.edad;
  const ambitoEdad = c ? `Comuna ${c.comuna}` : "toda la Ciudad";
  const edadEsDeLaComuna = Boolean(b && c);

  const feminidad = unidad.varones > 0 ? (unidad.mujeres / unidad.varones) * 100 : null;
  const densidadCiudad = datos.poblacion.densidad;

  /* El ranking se recorta por `nroComuna` y no por `comuna` a secas: entrando
     por una URL con `?barrio=...` la comuna del estado todavía es null —el
     tablero la fija al hacer clic, no al montar— y la lista quedaba mostrando
     los 48 barrios con el elegido fuera de la ventana visible.

     Sin `useMemo`: son 48 filas y el compilador de React memoriza esto solo.
     Escrito a mano no lo puede preservar, porque `nroComuna` sale de un
     `find`, y entonces deja de optimizar el componente entero. */
  const clave = vista === "poblacion" ? "poblacion" : "densidad";
  const ranking = datos.barrios
    .filter((x) => (nroComuna === null || x.comuna === nroComuna) && x[clave] != null)
    .sort((x, y) => (y[clave] as number) - (x[clave] as number));

  const maxRanking = ranking.length ? (ranking[0][vista] as number) : 1;

  const kpis = [
    {
      etiqueta: "Habitantes",
      valor: num(unidad.poblacion),
      nota: <>Censo {datos.poblacion.anio} · {ambito}
        {!b && !c ? "" : <> · {pct(share)} de la Ciudad</>}</>,
      ayuda: `Población residente según el Censo ${datos.poblacion.anio}, la fuente más fina `
           + "disponible (radio censal, ~800 habitantes). Es el denominador de la tasa de delito "
           + "del tablero. Hay un censo más nuevo, el de 2022, pero solo está publicado hasta "
           + "nivel comuna: por barrio no existe.",
    },
    {
      etiqueta: "Densidad",
      valor: unidad.densidad == null ? "—" : num(unidad.densidad),
      unidad: "hab/km²",
      nota: unidad.area_km2 == null ? "sin superficie"
        : <>{num1(unidad.area_km2)} km²{unidad.densidad != null && (b || c) ? <>
            {" · "}{unidad.densidad >= densidadCiudad ? "arriba" : "abajo"} del promedio de la Ciudad
          </> : <> · promedio de la Ciudad</>}</>,
      ayuda: `Habitantes por kilómetro cuadrado. La Ciudad promedia ${num(densidadCiudad)}, `
           + "pero el rango entre barrios es de más de veinte a uno: la densidad explica buena "
           + "parte de por qué dos barrios con el mismo conteo de delitos no son comparables.",
    },
    {
      etiqueta: "Mujeres cada 100 varones",
      valor: feminidad == null ? "—" : num(feminidad),
      nota: <>{pct(unidad.mujeres / unidad.poblacion)} mujeres · Censo {datos.poblacion.anio}</>,
      ayuda: "Índice de feminidad, el que publica INDEC. Arriba de 100 hay más mujeres que "
           + "varones. En toda la Ciudad da 117, y sube en los barrios más envejecidos porque "
           + "las mujeres viven más.",
    },
    {
      etiqueta: "Mayores de 65",
      valor: pct(edad.pct_65 / 100),
      nota: <>Censo {datos.edad.anio} · {ambitoEdad}
        {edadEsDeLaComuna && <span className="text-[var(--warn)]"> · no hay dato por barrio</span>}</>,
      ayuda: `Porcentaje de población de 65 años y más, Censo ${datos.edad.anio}. `
           + datos.notas.edad_solo_comuna + " " + datos.notas.edad_derivada,
    },
  ];

  return (
    <section className="card p-3 flex flex-col gap-3">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Quién vive acá
        </h2>
        <p className="text-[11px] text-ink-muted">
          {ambito} · sigue el filtro de comuna y de barrio. Población y sexo del Censo{" "}
          {datos.poblacion.anio}; edad, del Censo {datos.edad.anio}.
        </p>
      </div>

      <div className="grid gap-2 grid-cols-2 xl:grid-cols-4">
        {kpis.map((k) => <KpiCard key={k.etiqueta} {...k} />)}
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <PorEdad c={c} ciudad={datos.edad} ambito={ambitoEdad} anio={datos.edad.anio} />
          <PorSexo varones={unidad.varones} mujeres={unidad.mujeres} anio={datos.poblacion.anio} />
        </div>

        <div className="flex flex-col gap-2 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-ink-2">
              Barrios por {vista === "poblacion" ? "habitantes" : "densidad"}
              {nroComuna !== null && <span className="text-ink-muted"> · Comuna {nroComuna}</span>}
            </p>
            <div className="flex gap-1" role="group" aria-label="Ordenar barrios">
              {(["poblacion", "densidad"] as Vista[]).map((v) => (
                <button
                  key={v}
                  onClick={() => setVista(v)}
                  aria-pressed={v === vista}
                  className={`px-2 py-0.5 text-[10.5px] rounded cursor-pointer border transition-colors duration-150 ${
                    v === vista ? "border-transparent bg-brand text-white"
                                : "border-line text-ink-2 hover:border-line-strong"}`}
                >
                  {v === "poblacion" ? "Habitantes" : "hab/km²"}
                </button>
              ))}
            </div>
          </div>
          <RankingBarrios
            filas={ranking} vista={vista} max={maxRanking} activo={barrio}
            onBarrio={(n) => {
              onBarrio(n);
              const el = datos.barrios.find((x) => x.nombre === n);
              if (n && el?.comuna != null) onComuna(el.comuna);
            }}
          />
        </div>
      </div>

      <p className="text-[11px] text-ink-muted leading-snug border-t border-line pt-2.5">
        {datos.notas.dos_censos} {datos.notas.denominador}
      </p>
    </section>
  );
}

/* ------------------------------------------------------------ grupos de edad */

const GRUPOS = [
  { key: "0_14", label: "0 a 14", color: "var(--brand-soft)" },
  { key: "15_64", label: "15 a 64", color: "var(--brand)" },
  { key: "65", label: "65 y más", color: "var(--accent)" },
] as const;

function PorEdad({
  c, ciudad, ambito, anio,
}: {
  c: DemoComuna | undefined;
  ciudad: Demografia["edad"];
  ambito: string; anio: number;
}) {
  const fuente = c ?? ciudad;
  const partes = GRUPOS.map((g) => ({
    ...g,
    pct: fuente[`pct_${g.key}` as keyof typeof fuente] as number,
    hab: fuente[`hab_${g.key}` as keyof typeof fuente] as number,
    ciudadPct: ciudad[`pct_${g.key}` as keyof typeof ciudad] as number,
  }));

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] text-ink-2">
        Edad · <span className="text-ink-muted">{ambito}, Censo {anio}</span>
      </p>

      {/* una sola barra apilada y no tres barras: lo que se lee acá es el
          reparto, y tres barras sueltas obligan a sumarlas mentalmente */}
      <div className="flex h-6 rounded overflow-hidden" role="img"
           aria-label={partes.map((p) => `${p.label} años: ${num1(p.pct)}%`).join(", ")}>
        {partes.map((p) => (
          <div key={p.key} className="grid place-items-center min-w-0"
               style={{ width: `${p.pct}%`, background: p.color }}
               title={`${p.label} años: ${num(p.hab)} personas (${num1(p.pct)}%)`}>
            <span className="text-[10px] font-semibold text-white tabular truncate px-1">
              {p.pct >= 12 ? `${num1(p.pct)}%` : ""}
            </span>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-[3px]">
        {partes.map((p) => {
          const dif = p.pct - p.ciudadPct;
          return (
            <div key={p.key} className="flex items-center gap-2 text-[10.5px]">
              <span className="w-2.5 h-2.5 rounded-[2px] shrink-0" style={{ background: p.color }} />
              <span className="text-ink-2 w-14 shrink-0">{p.label}</span>
              <span className="tabular text-ink-2 w-16 text-right">{num(p.hab)}</span>
              <span className="tabular text-ink-muted w-12 text-right">{num1(p.pct)}%</span>
              {c && (
                <span className={`tabular text-[10px] ${
                  Math.abs(dif) < 0.5 ? "text-ink-muted"
                    : dif > 0 ? "text-[var(--accent)]" : "text-brand"}`}>
                  {Math.abs(dif) < 0.5 ? "= Ciudad"
                    : `${dif > 0 ? "+" : "−"}${num1(Math.abs(dif))} pp vs Ciudad`}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {c && (
        <p className="text-[10.5px] text-ink-muted leading-snug">
          Índice de envejecimiento <span className="tabular">{num(c.envejecimiento)}</span>
          {" "}({c.envejecimiento >= 100
            ? `hay ${num(c.envejecimiento)} personas de 65 y más cada 100 chicos de 0 a 14`
            : `hay más chicos que mayores`}) · {num1(c.pct_80)}% tiene 80 o más.
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------- sexo */

function PorSexo({ varones, mujeres, anio }: { varones: number; mujeres: number; anio: number }) {
  const total = varones + mujeres;
  if (total === 0) return null;
  const pv = (varones / total) * 100;

  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-[11px] text-ink-2">
        Sexo · <span className="text-ink-muted">Censo {anio}</span>
      </p>
      <div className="flex h-5 rounded overflow-hidden" role="img"
           aria-label={`Varones ${num1(pv)}%, mujeres ${num1(100 - pv)}%`}>
        <div className="grid place-items-center" style={{ width: `${pv}%`, background: "var(--brand)" }}
             title={`${num(varones)} varones (${num1(pv)}%)`}>
          <span className="text-[10px] font-semibold text-white tabular">{num1(pv)}%</span>
        </div>
        <div className="grid place-items-center"
             style={{ width: `${100 - pv}%`, background: "var(--risk-3)" }}
             title={`${num(mujeres)} mujeres (${num1(100 - pv)}%)`}>
          <span className="text-[10px] font-semibold text-white tabular">{num1(100 - pv)}%</span>
        </div>
      </div>
      <div className="flex gap-4 text-[10.5px] text-ink-2">
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: "var(--brand)" }} />
          {num(varones)} varones
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: "var(--risk-3)" }} />
          {num(mujeres)} mujeres
        </span>
      </div>
    </div>
  );
}

/* --------------------------------------------------------- ranking de barrios */

function RankingBarrios({
  filas, vista, max, activo, onBarrio,
}: {
  filas: DemoBarrio[]; vista: Vista; max: number;
  activo: string | null; onBarrio: (n: string | null) => void;
}) {
  return (
    <div className="flex flex-col gap-[2px] max-h-[15.5rem] overflow-auto scroll-fino pr-1">
      {filas.map((f) => {
        const v = f[vista] as number;
        const on = activo === f.nombre;
        return (
          <button
            key={f.nombre}
            onClick={() => onBarrio(on ? null : f.nombre)}
            aria-pressed={on}
            title={`${f.nombre}: ${num(f.poblacion)} habitantes` +
                   (f.densidad != null ? ` · ${num(f.densidad)} hab/km²` : "")}
            className="group grid grid-cols-[6.5rem_1fr_4rem] items-center gap-2 text-left
                       cursor-pointer rounded px-1 py-[2px] hover:bg-surface-sunk transition-colors duration-150"
          >
            <span className={`text-[10.5px] truncate ${on ? "text-brand font-semibold" : "text-ink-2"}`}>
              {f.nombre}
            </span>
            <span className="h-2.5 bg-surface-sunk rounded-sm overflow-hidden">
              <span className="block h-full rounded-sm transition-all duration-200"
                    style={{
                      width: `${(v / max) * 100}%`,
                      background: on ? "var(--brand)" : "var(--brand-soft)",
                      opacity: activo === null || on ? 1 : 0.35,
                    }} />
            </span>
            <span className="text-[10.5px] tabular text-ink-2 text-right">{num(v)}</span>
          </button>
        );
      })}
      {filas.length === 0 && (
        <p className="text-[11px] text-ink-muted px-1 py-3">No hay barrios para este filtro.</p>
      )}
    </div>
  );
}
