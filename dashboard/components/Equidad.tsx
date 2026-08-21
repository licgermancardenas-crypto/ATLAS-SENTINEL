"use client";

import type { EquidadCobertura } from "@/lib/types";
import { num, num1, pct } from "@/lib/formato";

/** Una brecha es una distancia, siempre positiva: `pp()` le pondría un "+"
 *  que la haría leer como una variación. */
const brechaPp = (v: number) => `${num1(v * 100)} pp`;

/* Cuánto cubre el plan ya está en la curva de arriba. Este panel contesta lo
   otro: **cómo lo reparte**.

   Existe porque la restricción de equidad del MCLP es un piso muy bajo —exige
   un solo hexágono cubierto por comuna— y cumplirla no dice nada sobre el
   reparto real. Un optimizador que maximiza un total tiene todos los
   incentivos para concentrar la cobertura donde es barata, y hasta ahora nadie
   podía ver si lo hacía.

   Lo hace: el plan cubre casi el doble de gente que las comisarías de hoy y
   duplica la brecha entre la comuna mejor y la peor cubierta. Cuatro comunas
   quedan **peor** que hoy. Eso no invalida el plan —cubre más en total, que
   es lo que se le pidió— pero es una consecuencia que tiene que estar a la
   vista antes de que alguien lo tome como una recomendación. */

export default function Equidad({
  datos, kPatrullas,
}: { datos: EquidadCobertura; kPatrullas: number }) {
  const plan = datos.planes[String(kPatrullas)];
  const resumenPlan = datos.curva.find((c) => c.k === kPatrullas);
  const hoy = new Map(datos.hoy.comunas.map((c) => [c.comuna, c]));

  if (!plan || !resumenPlan || resumenPlan.brecha == null) {
    return (
      <section className="card p-3">
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2 mb-1">
          Cómo se reparte esa cobertura
        </h2>
        <p className="text-[11px] text-ink-muted">
          Con {kPatrullas} patrullas no hay plan factible, así que no hay reparto que mirar.
        </p>
      </section>
    );
  }

  const filas = [...plan]
    .map((p) => ({ ...p, hoy: hoy.get(p.comuna)?.poblacion ?? 0 }))
    .sort((a, b) => b.poblacion - a.poblacion);
  const empeoran = filas.filter((f) => f.poblacion < f.hoy).length;
  const rh = datos.hoy.resumen;

  return (
    <section className="card p-3 flex flex-col gap-2.5">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Cómo se reparte esa cobertura
        </h2>
        <p className="text-[11px] text-ink-muted">
          Población cubierta dentro de cada comuna, sobre su propia población. Con {kPatrullas} patrullas.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <Dato etiqueta="Brecha hoy" valor={brechaPp(rh.brecha)}
              sub={`C${rh.peor_comuna} a C${rh.mejor_comuna}`} />
        <Dato etiqueta={`Brecha con ${kPatrullas}`} valor={brechaPp(resumenPlan.brecha)}
              sub={`C${resumenPlan.peor_comuna} a C${resumenPlan.mejor_comuna}`}
              alerta={resumenPlan.brecha > rh.brecha} />
        <Dato etiqueta="Comunas que empeoran" valor={`${empeoran} de ${filas.length}`}
              sub="contra la distribución actual" alerta={empeoran > 0} />
      </div>

      <Dumbbell filas={filas} />

      <p className="text-[10.5px] text-ink-muted leading-snug border-t border-line pt-2">
        La restricción de equidad del optimizador exige <strong>un</strong> hexágono cubierto por
        comuna, y eso es todo: cumplirla no impide concentrar el resto.{" "}
        {resumenPlan.brecha > rh.brecha ? (
          <>Con {kPatrullas} patrullas el plan cubre más gente que las comisarías de hoy pero la
            reparte peor —la brecha pasa de <span className="tabular">{brechaPp(rh.brecha)}</span> a{" "}
            <span className="tabular">{brechaPp(resumenPlan.brecha)}</span>—, y{" "}
            <span className="tabular">{resumenPlan.sin_cubrir}</span>{" "}
            {resumenPlan.sin_cubrir === 1 ? "comuna queda" : "comunas quedan"} abajo del{" "}
            {pct(datos.umbral_sin_cubrir, 0)} contra{" "}
            <span className="tabular">{rh.sin_cubrir}</span> hoy. </>
        ) : (
          <>Con {kPatrullas} patrullas el reparto queda más parejo que hoy. </>
        )}
        Cubrir más y repartir mejor son dos objetivos distintos, y el modelo solo optimiza el primero.
      </p>
    </section>
  );
}

function Dato({
  etiqueta, valor, sub, alerta,
}: { etiqueta: string; valor: string; sub: string; alerta?: boolean }) {
  return (
    <div className="rounded bg-surface-sunk px-2 py-1.5 flex flex-col gap-0.5">
      <span className="text-[9.5px] uppercase tracking-[0.06em] text-ink-muted leading-tight">
        {etiqueta}
      </span>
      <span className={`text-sm font-semibold tabular ${alerta ? "text-[var(--warn)]" : "text-ink"}`}>
        {valor}
      </span>
      <span className="text-[9.5px] text-ink-muted leading-tight">{sub}</span>
    </div>
  );
}

/* Un segmento por comuna entre lo que cubre hoy y lo que cubriría el plan. Es
   el mismo idioma que usa el panel de sensibilidad al radio, y acá gana algo
   más: el color del segmento dice la dirección, así que las comunas que
   pierden cobertura se ven sin tener que comparar dos rankings. */

function Dumbbell({
  filas,
}: { filas: { comuna: number; poblacion: number; hoy: number; habitantes: number }[] }) {
  const w = 420, alto = 19, arr = 22, aba = 8;
  const h = arr + filas.length * alto + aba;
  const x0 = 44, x1 = w - 14;
  const x = (v: number) => x0 + v * (x1 - x0);
  const y = (i: number) => arr + i * alto + alto / 2;
  const gris = "var(--pt-existente)";

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto" role="img" aria-label={
      `Cobertura de población por comuna, hoy contra el plan. ` +
      filas.map((f) => `Comuna ${f.comuna}: de ${pct(f.hoy)} a ${pct(f.poblacion)}.`).join(" ")}>
      {[0, 0.25, 0.5, 0.75, 1].map((v) => (
        <g key={v}>
          <line x1={x(v)} y1={arr - 6} x2={x(v)} y2={h - aba} stroke="var(--border)" strokeWidth="1" />
          <text x={x(v)} y={arr - 11} textAnchor="middle" fontSize="9.5"
                fill="var(--text-muted)" className="tabular">{pct(v, 0)}</text>
        </g>
      ))}

      {filas.map((f, i) => {
        const baja = f.poblacion < f.hoy;
        const color = baja ? "var(--warn)" : "var(--brand)";
        return (
          <g key={f.comuna}>
            <text x={x0 - 7} y={y(i) + 3.5} textAnchor="end" fontSize="10"
                  className="tabular" fill="var(--text-secondary)">
              C{f.comuna}
            </text>
            <line x1={x(f.hoy)} y1={y(i)} x2={x(f.poblacion)} y2={y(i)}
                  stroke={color} strokeWidth="3" strokeLinecap="round" opacity="0.45" />
            <circle cx={x(f.hoy)} cy={y(i)} r="3.5" fill={gris} />
            <circle cx={x(f.poblacion)} cy={y(i)} r="4" fill={color}
                    stroke="var(--surface-2)" strokeWidth="1.5" />
            <title>
              {`Comuna ${f.comuna}: hoy ${pct(f.hoy)} de su población cubierta, ` +
               `con el plan ${pct(f.poblacion)} (${num(f.habitantes)} personas). ` +
               (baja ? "Queda peor que hoy." : "Mejora.")}
            </title>
          </g>
        );
      })}

      <g transform={`translate(${x0}, ${h - 1})`}>
        <circle cx="4" cy="-3.5" r="3.5" fill={gris} />
        <text x="13" y="0" fontSize="9.5" fill="var(--text-muted)">hoy</text>
        <circle cx="52" cy="-3.5" r="4" fill="var(--brand)" />
        <text x="61" y="0" fontSize="9.5" fill="var(--text-muted)">mejora</text>
        <circle cx="118" cy="-3.5" r="4" fill="var(--warn)" />
        <text x="127" y="0" fontSize="9.5" fill="var(--text-muted)">empeora</text>
      </g>
    </svg>
  );
}
