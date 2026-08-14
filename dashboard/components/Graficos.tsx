"use client";

import { useMemo, useState } from "react";
import type { ComunaResumen, CurvaK, FilaSerie, SensibilidadRadio, Turno } from "@/lib/types";
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
  curva, kActual, onK,
}: { curva: CurvaK; kActual: number; onK: (k: number) => void }) {
  const puntos = curva.curva.filter((p) => p.cobertura !== null) as
    { k: number; cobertura: number; reusa_comisaria?: number }[];
  const w = 420, h = 190;
  const maxK = Math.max(...puntos.map((p) => p.k));
  const maxY = 0.8;
  const x = (k: number) => M.izq + (k / maxK) * (w - M.izq - M.der);
  const y = (v: number) => M.arr + (1 - v / maxY) * (h - M.arr - M.aba);

  const linea = "M" + puntos.map((p) => `${x(p.k).toFixed(1)},${y(p.cobertura).toFixed(1)}`).join(" L");
  const area = `${linea} L${x(maxK).toFixed(1)},${y(0).toFixed(1)} L${x(puntos[0].k).toFixed(1)},${y(0).toFixed(1)} Z`;
  const actual = curva.cobertura_actual;
  const sel = puntos.reduce((a, b) => (Math.abs(b.k - kActual) < Math.abs(a.k - kActual) ? b : a));

  return (
    <Marco w={w} h={h} etiqueta={
      `Curva de cobertura: con ${puntos[0].k} patrullas se cubre ${pct(puntos[0].cobertura)} del riesgo y ` +
      `con ${maxK} se cubre ${pct(puntos[puntos.length - 1].cobertura)}. Las ${curva.n_comisarias} ` +
      `comisarías actuales cubren ${pct(actual)}.`}>
      {[0, 0.2, 0.4, 0.6, 0.8].map((v) => (
        <g key={v}>
          <line x1={M.izq} y1={y(v)} x2={w - M.der} y2={y(v)} stroke="var(--border)" strokeWidth="1" />
          <text x={M.izq - 7} y={y(v) + 3.5} textAnchor="end" fontSize="10"
                fill="var(--text-muted)" className="tabular">{pct(v, 0)}</text>
        </g>
      ))}

      <path d={area} fill="var(--brand-wash)" />
      <path d={linea} fill="none" stroke="var(--brand)" strokeWidth="2" strokeLinejoin="round" />

      {/* referencia: lo que cubre hoy la infraestructura fija */}
      <line x1={M.izq} y1={y(actual)} x2={w - M.der} y2={y(actual)}
            stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="4 3" />
      <text x={M.izq + 5} y={y(actual) - 5} fontSize="9.5" fill="var(--accent)" className="tabular">
        {curva.n_comisarias} comisarías hoy · {pct(actual)}
      </text>

      <line x1={x(sel.k)} y1={M.arr} x2={x(sel.k)} y2={y(0)} stroke="var(--brand)"
            strokeWidth="1" strokeDasharray="3 3" opacity="0.55" />
      <circle cx={x(sel.k)} cy={y(sel.cobertura)} r="5" fill="var(--brand)"
              stroke="var(--surface-2)" strokeWidth="2" />

      {puntos.map((p) => (
        <g key={p.k}>
          <circle cx={x(p.k)} cy={y(p.cobertura)} r="3" fill="var(--brand)" opacity={p.k === sel.k ? 0 : 0.55} />
          <rect x={x(p.k) - 12} y={M.arr} width="24" height={h - M.arr - M.aba}
                fill="transparent" className="cursor-pointer" tabIndex={0} role="button"
                aria-label={`${p.k} patrullas, ${pct(p.cobertura)} de cobertura`}
                onClick={() => onK(p.k)} onFocus={() => onK(p.k)} />
        </g>
      ))}

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

/* -------------------------------------------------------- barras por comuna */

export function BarrasComuna({
  comunas, turno, seleccion, onSeleccion,
}: {
  comunas: ComunaResumen[]; turno: Turno;
  seleccion: number | null; onSeleccion: (c: number | null) => void;
}) {
  const clave = `riesgo_${turno}` as keyof ComunaResumen;
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
      <text x={340} y={arr - 11} textAnchor="start" fontSize="9.5" fill="var(--text-muted)">
        mismo plan
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
                    (solape != null ? ` · ${pct(solape, 0)} de las ubicaciones coincide con el plan de 800 m` : "")}</title>
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

const TIPOS_ORDEN = ["Robo", "Hurto", "Lesiones", "Amenazas", "Vialidad"];
const COLOR_TIPO: Record<string, string> = {
  Robo: "var(--risk-5)", Hurto: "var(--risk-4)", Lesiones: "var(--risk-3)",
  Amenazas: "var(--risk-2)", Vialidad: "var(--brand-soft)",
};

export function SerieAnual({ serie }: { serie: FilaSerie[] }) {
  const [tipo, setTipo] = useState<string>("Robo");
  const w = 420, h = 170;

  const porMes = useMemo(() => {
    const m = new Map<string, number>();
    serie.filter((f) => f.tipo === tipo && f.anio >= 2024)
      .forEach((f) => m.set(`${f.anio}-${f.mes}`, f.n));
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
      <div className="flex gap-1 flex-wrap">
        {TIPOS_ORDEN.map((t) => (
          <button
            key={t}
            onClick={() => setTipo(t)}
            className={`px-2 py-0.5 text-[10.5px] rounded cursor-pointer border transition-colors duration-150 ${
              t === tipo
                ? "border-transparent text-white"
                : "border-line text-ink-2 hover:border-line-strong"
            }`}
            style={t === tipo ? { background: COLOR_TIPO[t] } : undefined}
          >
            {t}
          </button>
        ))}
      </div>
      <Marco w={w} h={h} etiqueta={`Serie mensual de ${tipo} en 2024 y 2025.`}>
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
              <title>{`${f.etiqueta}: ${num(f.n)} ${tipo.toLowerCase()}`}</title>
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
