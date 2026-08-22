"use client";

import { useMemo } from "react";
import type {
  CoberturaPoblacion, ComunaResumen, CurvaK, FilaSerie, SensibilidadRadio, TipoDelito, Turno,
} from "@/lib/types";
import { claveRiesgo, TIPOS, tipoInfo } from "@/lib/types";
import { MESES, num, num1, pct, pp } from "@/lib/formato";

/* Gráficos en SVG a mano, sin librería. Son tres formas simples y una
   dependencia de charts pesa más que todo el resto del bundle junto. Reglas que
   se respetan en los tres: grilla de bajo contraste, cifras tabulares,
   tooltip accesible por teclado y nunca color como único portador de sentido. */

const M = { izq: 46, der: 12, arr: 14, aba: 30 };

function Marco({ w, h, children, etiqueta }: {
  w: number; h: number; children: React.ReactNode; etiqueta: string;
}) {
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto" role="img" aria-label={etiqueta}>
      {children}
    </svg>
  );
}

/* ---------------------------------------------------------------- curva K */

export function CurvaCobertura({
  curva, pob, kActual, onK,
}: { curva: CurvaK; pob: CoberturaPoblacion; kActual: number; onK: (k: number) => void }) {
  const puntos = curva.curva.filter((p) => p.cobertura !== null) as
    { k: number; cobertura: number; reusa_comisaria?: number }[];
  const w = 420, h = 205;
  const maxK = Math.max(...puntos.map((p) => p.k));
  const maxY = 0.8;
  const x = (k: number) => M.izq + (k / maxK) * (w - M.izq - M.der);
  const y = (v: number) => M.arr + (1 - v / maxY) * (h - M.arr - M.aba);

  const linea = "M" + puntos.map((p) => `${x(p.k).toFixed(1)},${y(p.cobertura).toFixed(1)}`).join(" L");
  const area = `${linea} L${x(maxK).toFixed(1)},${y(0).toFixed(1)} L${x(puntos[0].k).toFixed(1)},${y(0).toFixed(1)} Z`;
  const actual = curva.cobertura_actual;
  const sel = puntos.reduce((a, b) => (Math.abs(b.k - kActual) < Math.abs(a.k - kActual) ? b : a));

  /* Las dos series usan los slots categóricos del sistema, en orden. No se
     eligen "a ojo que se vean distintas": el par anterior —azul de marca e
     índigo de las capas demográficas— quedaba en ΔE 14,2 para visión normal,
     abajo del piso de 15. Este da 32,1. Ver el comentario de --serie-1. */
  const pobPuntos = pob.curva.filter((p) => p.poblacion !== null) as
    { k: number; poblacion: number; habitantes?: number }[];
  const lineaPob = "M" + pobPuntos.map((p) => `${x(p.k).toFixed(1)},${y(p.poblacion).toFixed(1)}`).join(" L");
  const selPob = pobPuntos.reduce((a, b) => (Math.abs(b.k - kActual) < Math.abs(a.k - kActual) ? b : a));
  const serie2 = "var(--serie-2)";

  return (
    <Marco w={w} h={h} etiqueta={
      `Dos curvas de cobertura contra la cantidad de patrullas. Con ${maxK} unidades se cubre ` +
      `${pct(puntos[puntos.length - 1].cobertura)} del riesgo pero ` +
      `${pct(pobPuntos[pobPuntos.length - 1].poblacion)} de la población. Las ` +
      `${curva.n_comisarias} comisarías actuales cubren ${pct(actual)} del riesgo y ` +
      `${pct(pob.actual.poblacion)} de la población.`}>
      {[0, 0.2, 0.4, 0.6, 0.8].map((v) => (
        <g key={v}>
          <line x1={M.izq} y1={y(v)} x2={w - M.der} y2={y(v)} stroke="var(--border)" strokeWidth="1" />
          <text x={M.izq - 7} y={y(v) + 3.5} textAnchor="end" fontSize="10"
                fill="var(--text-muted)" className="tabular">{pct(v, 0)}</text>
        </g>
      ))}

      <path d={area} fill="var(--serie-1-wash)" />
      <path d={linea} fill="none" stroke="var(--serie-1)" strokeWidth="2" strokeLinejoin="round" />
      <path d={lineaPob} fill="none" stroke={serie2} strokeWidth="2" strokeLinejoin="round" />

      {/* Las dos referencias de "hoy". Van en el gris de "infraestructura que
          ya existe" —el mismo de los puntos de comisarías en el mapa— y no en
          el ámbar de acento, que estaba a un paso de --risk-4 y hacía que una
          línea de referencia se leyera como una clase del mapa. Una referencia
          no es una serie: no le corresponde un slot categórico. */}
      <line x1={M.izq} y1={y(actual)} x2={w - M.der} y2={y(actual)}
            stroke="var(--pt-existente)" strokeWidth="1.5" strokeDasharray="4 3" />
      <text x={M.izq + 5} y={y(actual) - 5} fontSize="9.5" fill="var(--text-secondary)" className="tabular">
        hoy · {pct(actual)} del riesgo
      </text>
      <line x1={M.izq} y1={y(pob.actual.poblacion)} x2={w - M.der} y2={y(pob.actual.poblacion)}
            stroke="var(--pt-existente)" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.6" />
      <text x={M.izq + 5} y={y(pob.actual.poblacion) - 5} fontSize="9.5"
            fill="var(--text-secondary)" className="tabular">
        hoy · {pct(pob.actual.poblacion)} de la gente
      </text>

      <line x1={x(sel.k)} y1={M.arr} x2={x(sel.k)} y2={y(0)} stroke="var(--serie-1)"
            strokeWidth="1" strokeDasharray="3 3" opacity="0.55" />
      <circle cx={x(sel.k)} cy={y(sel.cobertura)} r="5" fill="var(--serie-1)"
              stroke="var(--surface-2)" strokeWidth="2" />
      <circle cx={x(selPob.k)} cy={y(selPob.poblacion)} r="5" fill={serie2}
              stroke="var(--surface-2)" strokeWidth="2" />

      {puntos.map((p) => {
        const pp = pobPuntos.find((q) => q.k === p.k);
        return (
          <g key={p.k}>
            <circle cx={x(p.k)} cy={y(p.cobertura)} r="3" fill="var(--serie-1)"
                    opacity={p.k === sel.k ? 0 : 0.55} />
            {pp && <circle cx={x(pp.k)} cy={y(pp.poblacion)} r="3" fill={serie2}
                           opacity={pp.k === selPob.k ? 0 : 0.55} />}
            <rect x={x(p.k) - 12} y={M.arr} width="24" height={h - M.arr - M.aba}
                  fill="transparent" className="cursor-pointer" tabIndex={0} role="button"
                  aria-label={`${p.k} patrullas: ${pct(p.cobertura)} del riesgo` +
                              (pp ? `, ${pct(pp.poblacion)} de la población` : "")}
                  onClick={() => onK(p.k)} onFocus={() => onK(p.k)} />
          </g>
        );
      })}

      {[0, 30, 60, 90, maxK].map((k) => (
        <text key={k} x={x(k)} y={h - 12} textAnchor="middle" fontSize="10"
              fill="var(--text-muted)" className="tabular">{k}</text>
      ))}
      <text x={(M.izq + w - M.der) / 2} y={h - 1} textAnchor="middle" fontSize="9.5" fill="var(--text-muted)">
        patrullas desplegadas
      </text>
    </Marco>
  );
}

/* La brecha entre las dos curvas no es un detalle de presentación: es una
   decisión de política que hasta ahora vivía adentro del optimizador sin estar
   a la vista de nadie que mirara el tablero. */

export function BrechaCobertura({
  pob, kActual,
}: { pob: CoberturaPoblacion; kActual: number }) {
  const p = pob.curva.find((q) => q.k === kActual) ?? pob.curva.find((q) => q.poblacion !== null);
  if (!p || p.poblacion === null || p.riesgo === null) return null;

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex gap-4 flex-wrap text-[10.5px]">
        <span className="inline-flex items-center gap-1.5 text-ink-2">
          <span className="w-3 h-[2px] rounded" style={{ background: "var(--serie-1)" }} />
          riesgo cubierto
        </span>
        <span className="inline-flex items-center gap-1.5 text-ink-2">
          <span className="w-3 h-[2px] rounded" style={{ background: "var(--serie-2)" }} />
          población cubierta
        </span>
      </div>
      <p className="text-[11px] text-ink-2 leading-snug">
        Con <strong className="tabular">{p.k}</strong> patrullas el plan cubre{" "}
        <strong className="tabular">{pct(p.riesgo)}</strong> del riesgo y{" "}
        <strong className="tabular">{pct(p.poblacion)}</strong> de la población:{" "}
        <strong className="tabular">{num(p.habitantes ?? 0)}</strong> personas a menos de{" "}
        {pob.radio_m} m de calle de un puesto.
      </p>
      {p.poblacion_si_optimiza_poblacion != null && p.riesgo_si_optimiza_poblacion != null && (
        <p className="text-[10.5px] text-ink-muted leading-snug">
          El riesgo siempre queda más cubierto que la gente, porque no están repartidos igual:
          el microcentro concentra delito con poca gente viviendo ahí. Optimizando población en
          vez de riesgo, el mismo presupuesto cubriría{" "}
          <span className="tabular">{pct(p.poblacion_si_optimiza_poblacion)}</span> de los
          habitantes pero solo <span className="tabular">{pct(p.riesgo_si_optimiza_poblacion)}</span>{" "}
          del riesgo
          {p.solape_planes != null && <>, y solo <span className="tabular">
            {pct(p.solape_planes, 0)}</span> de las ubicaciones coincidiría</>}
          . Cuál de los dos objetivos se elige es una decisión de política, no del modelo.
        </p>
      )}
    </div>
  );
}

/* ¿A quién llega el plan? Es la versión operacionalizable de la pregunta que
   dejó abierta la auditoría de equidad, y la única que estos datos permiten
   contestar: no se puede saber a quién le roban —los delitos no traen ningún
   atributo del damnificado— pero sí quién queda cerca de un puesto.

   El resultado contradice lo que uno esperaría: los hogares con NBI quedan
   **mejor** cubiertos que el residente promedio, no peor. Tiene explicación —
   el NBI se concentra en el corredor sureste (Constitución, La Boca,
   Monserrat, Barracas) que es también donde se concentra el delito
   registrado, así que optimizar por riesgo aterriza ahí.

   Y el mismo número admite dos lecturas opuestas, así que el panel las pone
   las dos en vez de elegir una. */

export function Vulnerables({
  pob, kActual,
}: { pob: CoberturaPoblacion; kActual: number }) {
  const p = pob.curva.find((q) => q.k === kActual);
  if (!p || p.poblacion == null || p.nbi == null || p.mayores == null) return null;
  const a = pob.actual;

  const filas = [
    { etiqueta: "Población", hoy: a.poblacion, plan: p.poblacion,
      universo: `${num(pob.poblacion_total)} habitantes` },
    { etiqueta: "Hogares con NBI", hoy: a.nbi, plan: p.nbi,
      universo: `${num(pob.poblacion_vulnerable.hogares_nbi)} hogares`, destacar: true },
    { etiqueta: "Mayores de 65", hoy: a.mayores, plan: p.mayores,
      universo: `${num(pob.poblacion_vulnerable.mayores_65)} personas · estimado`, flojo: true },
  ];

  return (
    <div className="flex flex-col gap-1.5 border-t border-line pt-2.5">
      <p className="text-[11px] text-ink-2">¿A quién llega esa cobertura?</p>

      <table className="w-full text-[10.5px] border-collapse">
        <thead>
          <tr className="text-ink-muted">
            <th scope="col" className="text-left font-normal pb-1">Grupo</th>
            <th scope="col" className="text-right font-normal pb-1">Hoy</th>
            <th scope="col" className="text-right font-normal pb-1 tabular">Con {kActual}</th>
            <th scope="col" className="text-right font-normal pb-1">Sobre</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.etiqueta} className={f.flojo ? "text-ink-muted" : "text-ink-2"}>
              <th scope="row" className={`text-left font-normal py-[1px] pr-2 ${
                f.destacar ? "text-brand font-semibold" : ""}`}>
                {f.etiqueta}
              </th>
              <td className="text-right tabular py-[1px]">{pct(f.hoy)}</td>
              <td className={`text-right tabular py-[1px] ${
                f.destacar ? "text-brand font-semibold" : ""}`}>{pct(f.plan)}</td>
              <td className="text-right py-[1px] text-ink-muted">{f.universo}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="text-[10.5px] text-ink-muted leading-snug">
        Los hogares con NBI quedan <strong>mejor</strong> cubiertos que el residente promedio, no
        peor: el NBI se concentra en el corredor sureste, que es también donde se concentra el
        delito registrado, así que optimizar por riesgo aterriza ahí. El mismo número se puede
        leer de dos formas opuestas —que el plan alcanza a quien más lo necesita, o que la
        vigilancia se concentra donde hay pobreza, que es justo el riesgo de retroalimentación
        que señala la literatura— y este dato no decide entre las dos: solo las vuelve precisas.
      </p>
      <p className="text-[10.5px] text-ink-muted leading-snug">
        La fila de mayores no aporta señal propia: la edad solo existe por comuna, así que dentro
        de cada una la tasa es constante y el número termina siguiendo a la población. Va igual
        para que se vea que se miró.
      </p>
    </div>
  );
}

/* -------------------------------------------------------- barras por comuna */

export function BarrasComuna({
  comunas, turno, tipo, seleccion, onSeleccion,
}: {
  comunas: ComunaResumen[]; turno: Turno; tipo: TipoDelito;
  seleccion: number | null; onSeleccion: (c: number | null) => void;
}) {
  const clave = claveRiesgo(turno, tipo);
  const orden = useMemo(
    () => [...comunas].sort((a, b) => (b[clave] as number) - (a[clave] as number)),
    [comunas, clave],
  );
  const max = Math.max(...orden.map((c) => c[clave] as number)) || 1;

  return (
    <div className="flex flex-col gap-[3px]">
      {orden.map((c) => {
        const v = c[clave] as number;
        const activa = seleccion === c.comuna;
        return (
          <button
            key={c.comuna}
            onClick={() => onSeleccion(activa ? null : c.comuna)}
            className="group grid grid-cols-[3.6rem_1fr_3.6rem] items-center gap-2 text-left
                       cursor-pointer rounded px-1 py-[3px] hover:bg-surface-sunk transition-colors duration-150"
            aria-pressed={activa}
          >
            <span className={`text-[11px] tabular ${activa ? "text-brand font-semibold" : "text-ink-2"}`}>
              Com. {c.comuna}
            </span>
            <span className="h-3 bg-surface-sunk rounded-sm overflow-hidden">
              <span
                className="block h-full rounded-sm transition-all duration-200"
                style={{
                  width: `${(v / max) * 100}%`,
                  background: activa ? "var(--brand)" : "var(--brand-soft)",
                  opacity: seleccion === null || activa ? 1 : 0.35,
                }}
              />
            </span>
            <span className="text-[11px] tabular text-ink-2 text-right">{num1(v * 100)}</span>
          </button>
        );
      })}
    </div>
  );
}

/* ---------------------------------------------------- sensibilidad al radio */

/* La pregunta que un jefe operativo hace primero es "¿y si el radio no es 800?".
   El barrido tiene dos respuestas distintas y hay que poder verlas juntas: la
   ganancia (el largo del segmento) se sostiene en todos los radios, pero el
   plan concreto (la columna de solape) se desarma apenas uno se mueve de 800.
   Por eso van en el mismo gráfico y no en dos. */

export function SensibilidadAlRadio({ datos }: { datos: SensibilidadRadio }) {
  const filas = datos.radios;
  const w = 420, alto = 22, arr = 30, aba = 26;
  const h = arr + filas.length * alto + aba;
  const x0 = 44, x1 = 300;
  const x = (v: number) => x0 + v * (x1 - x0);
  const y = (i: number) => arr + i * alto + alto / 2;

  const gris = "var(--pt-existente)";

  return (
    <Marco w={w} h={h} etiqueta={
      `Sensibilidad al radio de cobertura. En los ${filas.length} radios probados, ` +
      `pasar a ${datos.k_titular} patrullas suma entre ${pp(Math.min(...filas.map((f) => f.ganancia_pp ?? 0)))} y ` +
      `${pp(Math.max(...filas.map((f) => f.ganancia_pp ?? 0)))} de cobertura, pero la coincidencia de ` +
      `ubicaciones contra el plan de 800 m baja hasta ` +
      `${pct(Math.min(...filas.map((f) => f.solape_plan_vs_800 ?? 1)))}.`}>
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={x(v)} y1={arr - 6} x2={x(v)} y2={h - aba} stroke="var(--border)" strokeWidth="1" />
          <text x={x(v)} y={arr - 11} textAnchor="middle" fontSize="9.5"
                fill="var(--text-muted)" className="tabular">{pct(v, 0)}</text>
        </g>
      ))}
      <text x={330} y={arr - 11} textAnchor="start" fontSize="9.5" fill="var(--text-muted)">
        coinciden
      </text>

      {filas.map((f, i) => {
        const hoy = f.cobertura_actual;
        const con = f.cobertura_k_titular ?? hoy;
        const solape = f.solape_plan_vs_800;
        const titular = f.radio_m === 800;
        return (
          <g key={f.radio_m}>
            <text x={x0 - 7} y={y(i) + 3.5} textAnchor="end" fontSize="10"
                  className="tabular"
                  fill={titular ? "var(--brand)" : "var(--text-secondary)"}
                  fontWeight={titular ? 600 : 400}>
              {f.radio_m} m
            </text>

            <line x1={x(hoy)} y1={y(i)} x2={x(con)} y2={y(i)}
                  stroke="var(--brand)" strokeWidth="3" strokeLinecap="round" opacity="0.5" />
            <circle cx={x(hoy)} cy={y(i)} r="3.5" fill={gris} />
            <circle cx={x(con)} cy={y(i)} r="4" fill="var(--brand)"
                    stroke="var(--surface-2)" strokeWidth="1.5" />

            {/* el solape va como barra y como número: la barra deja ver de un
                vistazo que se derrumba, el número evita tener que estimarlo */}
            {solape != null && (
              <>
                <rect x={340} y={y(i) - 4} width={44} height={8} rx="1.5" fill="var(--surface-sunk)" />
                <rect x={340} y={y(i) - 4} width={44 * solape} height={8} rx="1.5"
                      fill={solape >= 0.6 ? "var(--brand-soft)" : "var(--warn)"} />
                <text x={w - 4} y={y(i) + 3.5} textAnchor="end" fontSize="9.5"
                      fill="var(--text-secondary)" className="tabular">{pct(solape, 0)}</text>
              </>
            )}
            <title>{`${f.radio_m} m — hoy ${pct(hoy)}, con ${datos.k_titular} patrullas ${pct(con)}` +
                    (solape != null ? ` · ${pct(solape, 0)} de las ubicaciones son las mismas que a 800 m` : "")}</title>
          </g>
        );
      })}

      <g transform={`translate(${x0}, ${h - 8})`}>
        <circle cx="4" cy="-3.5" r="3.5" fill={gris} />
        <text x="13" y="0" fontSize="9.5" fill="var(--text-muted)">hoy</text>
        <circle cx="52" cy="-3.5" r="4" fill="var(--brand)" />
        <text x="61" y="0" fontSize="9.5" fill="var(--text-muted)">
          con {datos.k_titular} patrullas
        </text>
      </g>
    </Marco>
  );
}

/* ------------------------------------------------------------ serie de tipos */

const COLOR_TIPO: Record<TipoDelito, string> = {
  todos: "var(--brand)", robo: "var(--risk-5)", hurto: "var(--risk-4)",
  lesiones: "var(--risk-3)", amenazas: "var(--risk-2)",
  vialidad: "var(--brand-soft)", homicidios: "var(--bad)",
};

/* Las solapas de acá son el mismo estado que el selector del encabezado, no una
   copia local. Antes eran independientes, y con un filtro global de tipo eso
   deja el tablero diciendo "Robo" arriba y "Hurto" abajo en la misma pantalla. */

export function SerieAnual({
  serie, tipo, onTipo,
}: { serie: FilaSerie[]; tipo: TipoDelito; onTipo: (t: TipoDelito) => void }) {
  const w = 420, h = 170;

  const porMes = useMemo(() => {
    const m = new Map<string, number>();
    const etiqueta = tipo === "todos" ? null : tipoInfo(tipo).label;
    serie.filter((f) => f.anio >= 2024 && (etiqueta === null || f.tipo === etiqueta))
      .forEach((f) => {
        const k = `${f.anio}-${f.mes}`;
        m.set(k, (m.get(k) ?? 0) + f.n);   // con "todos" hay una fila por tipo: se suman
      });
    const filas: { etiqueta: string; anio: number; n: number }[] = [];
    for (const anio of [2024, 2025])
      for (let mes = 1; mes <= 12; mes++)
        filas.push({ etiqueta: `${MESES[mes - 1]} ${String(anio).slice(2)}`, anio, n: m.get(`${anio}-${mes}`) ?? 0 });
    return filas;
  }, [serie, tipo]);

  const max = Math.max(...porMes.map((f) => f.n)) * 1.12 || 1;
  const bw = (w - M.izq - M.der) / porMes.length;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1 flex-wrap" role="group" aria-label="Tipo de delito">
        {TIPOS.map((t) => (
          <button
            key={t.key}
            onClick={() => onTipo(t.key)}
            aria-pressed={t.key === tipo}
            title={t.nota}
            className={`px-2 py-0.5 text-[10.5px] rounded cursor-pointer border transition-colors duration-150 ${
              t.key === tipo
                ? "border-transparent text-white"
                : "border-line text-ink-2 hover:border-line-strong"
            }`}
            style={t.key === tipo ? { background: COLOR_TIPO[t.key] } : undefined}
          >
            {t.key === "todos" ? "Todos" : t.label}
          </button>
        ))}
      </div>
      <Marco w={w} h={h} etiqueta={
        `Serie mensual de ${tipo === "todos" ? "delitos de todos los tipos" : tipoInfo(tipo).label.toLowerCase()} ` +
        `en 2024 y 2025.`}>
        {[0, 0.5, 1].map((f) => {
          const yy = M.arr + (1 - f) * (h - M.arr - M.aba);
          return (
            <g key={f}>
              <line x1={M.izq} y1={yy} x2={w - M.der} y2={yy} stroke="var(--border)" strokeWidth="1" />
              <text x={M.izq - 7} y={yy + 3.5} textAnchor="end" fontSize="10"
                    fill="var(--text-muted)" className="tabular">{num(max * f)}</text>
            </g>
          );
        })}
        {porMes.map((f, i) => {
          const alto = (f.n / max) * (h - M.arr - M.aba);
          return (
            <rect key={i} x={M.izq + i * bw + 1} y={h - M.aba - alto} width={bw - 2} height={alto}
                  fill={f.anio === 2025 ? COLOR_TIPO[tipo] : "var(--border-strong)"} rx="1">
              <title>{`${f.etiqueta}: ${num(f.n)} ${tipo === "todos" ? "delitos" : tipoInfo(tipo).label.toLowerCase()}`}</title>
            </rect>
          );
        })}
        <line x1={M.izq + 12 * bw} y1={M.arr} x2={M.izq + 12 * bw} y2={h - M.aba}
              stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3 2" />
        <text x={M.izq + 6 * bw} y={h - 16} textAnchor="middle" fontSize="10" fill="var(--text-muted)">2024</text>
        <text x={M.izq + 18 * bw} y={h - 16} textAnchor="middle" fontSize="10" fill="var(--text-muted)">2025</text>
      </Marco>
      <p className="text-[10.5px] text-ink-muted leading-snug">
        Gris 2024, color 2025. El nivel de 2025 está bajo revisión: ver salvedades.
      </p>
    </div>
  );
}
