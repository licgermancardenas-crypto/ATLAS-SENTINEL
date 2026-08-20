"use client";

import { useMemo, useState } from "react";
import type { FilaSerie, MesPronostico, Pronostico as DatosPronostico, TipoDelito } from "@/lib/types";
import { tipoInfo } from "@/lib/types";
import { delta, MESES, num } from "@/lib/formato";

/* El pronóstico mensual contesta la pregunta que el resto del tablero no
   contesta: no *dónde* va a haber delito sino *cuánto* va a haber en toda la
   Ciudad. Es otra unidad de análisis —una serie única de 120 meses, no la
   grilla— y eso obliga a tres decisiones de interfaz:

   1. **No sigue el filtro de comuna ni el de barrio.** La serie modelada es de
      Ciudad entera; recortarla por territorio sería inventar el dato. El panel
      lo dice en lugar de dejar que alguien suponga que el número se está
      filtrando junto con el resto.
   2. **Van los cuatro modelos, no solo el que se usa.** El hallazgo del
      backtest es que el ganador cambia con el horizonte y que a doce meses no
      hay nada que le gane al baseline. Mostrar un solo modelo escondería justo
      eso y haría parecer el pronóstico más firme de lo que es.
   3. **El error va pegado al número, no en una nota al pie.** "10.993 por mes"
      sin "±971 en un mes normal, y 1.360 el año del quiebre" es una precisión
      falsa. */

const M = { izq: 46, der: 12, arr: 14, aba: 30 };

/** Meses de historia que se dibujan antes del pronóstico. Dos años: uno menos
 *  deja al pronóstico sin contra qué compararse visualmente, y tres apretan
 *  tanto las columnas que el quiebre de 2025 deja de leerse. */
const MESES_HISTORIA = 24;

export default function Pronostico({
  datos, serie, tipo,
}: { datos: DatosPronostico; serie: FilaSerie[]; tipo: TipoDelito }) {
  const [modeloKey, setModeloKey] = useState(datos.elegido);

  const esAgregado = tipo === "todos";
  const modelo = datos.modelos.find((m) => m.key === modeloKey) ?? datos.modelos[0];
  const elegido = datos.modelos.find((m) => m.key === datos.elegido) ?? datos.modelos[0];
  const porTipo = datos.por_tipo.find((t) => t.key === tipo);

  /* Con el filtro por tipo puesto se muestra la serie de ese tipo, que corre
     solo con el modelo elegido. El selector de modelos desaparece en vez de
     quedar deshabilitado: un control que no hace nada invita a buscarle la
     falla. */
  const proy: MesPronostico[] = esAgregado ? modelo.meses : (porTipo?.meses ?? []);
  const mensual = esAgregado ? modelo.mensual : (porTipo?.mensual ?? 0);
  const base = esAgregado ? datos.base.mensual : (porTipo?.base_mensual ?? 0);
  const vs = esAgregado ? modelo.vs_base : porTipo?.vs_base ?? null;
  const banda = esAgregado ? modelo.banda : (porTipo?.banda ?? [0, 0]);

  /* Los últimos 24 meses observados, del mismo tipo que el pronóstico. Se arman
     acá y no se piden al export: `serie_delitos.json` ya los tiene y duplicar
     la serie en dos archivos es la forma más barata de que un día no coincidan. */
  const historia = useMemo(() => {
    const etiqueta = esAgregado ? null : tipoInfo(tipo).label;
    const m = new Map<string, number>();
    serie.filter((f) => etiqueta === null || f.tipo === etiqueta)
      .forEach((f) => m.set(`${f.anio}-${f.mes}`, (m.get(`${f.anio}-${f.mes}`) ?? 0) + f.n));

    const filas: { anio: number; mes: number; n: number }[] = [];
    for (let i = MESES_HISTORIA; i >= 1; i--) {
      const total = (datos.anio - 1) * 12 + 12 - i;       // meses absolutos hacia atrás
      const anio = Math.floor(total / 12);
      const mes = (total % 12) + 1;
      filas.push({ anio, mes, n: m.get(`${anio}-${mes}`) ?? 0 });
    }
    return filas;
  }, [serie, tipo, esAgregado, datos.anio]);

  /* Homicidios son ~5 hechos por mes: la banda es más ancha que el pronóstico y
     el signo de la variación se da vuelta con dos casos. Mismo criterio y mismo
     umbral que el panel de "cuándo ocurren". */
  const pocosCasos = mensual * 12 < 1000;

  if (proy.length === 0) {
    return null;
  }

  return (
    <section className="card p-3 flex flex-col gap-3">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Cuánto delito registrado en {datos.anio}
        </h2>
        <p className="text-[11px] text-ink-muted">
          Toda la Ciudad, mes a mes. No sigue el filtro de comuna ni de barrio: la serie
          se modela entera y recortarla por territorio sería inventar el dato.
        </p>
      </div>

      {esAgregado && (
        <div className="flex gap-1 flex-wrap" role="group" aria-label="Modelo de pronóstico">
          {datos.modelos.map((m) => (
            <button
              key={m.key}
              onClick={() => setModeloKey(m.key)}
              aria-pressed={m.key === modeloKey}
              title={`${m.nota} Error típico ${num(m.mae_normal)} delitos por mes en meses normales.`}
              className={`px-2 py-0.5 text-[10.5px] rounded cursor-pointer border transition-colors duration-150 ${
                m.key === modeloKey
                  ? "border-transparent bg-brand text-white"
                  : "border-line text-ink-2 hover:border-line-strong"
              }`}
            >
              {m.label}
              {m.key === datos.elegido && <span aria-label=" (el que se usa)"> ★</span>}
            </button>
          ))}
        </div>
      )}

      <Curva historia={historia} proy={proy} base={base} anio={datos.anio}
             etiquetaTipo={esAgregado ? "delitos" : tipoInfo(tipo).label.toLowerCase()} />

      {/* el número grande y su error, juntos y en ese orden */}
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className="flex items-baseline gap-1.5">
            <span className="text-[26px] leading-none font-semibold tabular">{num(mensual)}</span>
            <span className="text-sm text-ink-muted">/ mes</span>
            {vs !== null && (
              <span className={`text-[12px] font-semibold tabular ${
                pocosCasos ? "text-ink-muted" : "text-[var(--warn)]"}`}>
                {delta(vs)}
              </span>
            )}
          </div>
          <p className="text-[11px] text-ink-muted mt-1">
            contra {num(base)} / mes en {datos.base.anio} · banda 90%{" "}
            <span className="tabular">{num(banda[0])}–{num(banda[1])}</span>
          </p>
        </div>

        {esAgregado && (
          <div className="text-right shrink-0">
            <p className="text-[11px] text-ink-2">
              Error típico <strong className="tabular">±{num(modelo.mae_normal)}</strong> por mes
            </p>
            <p className="text-[11px] text-ink-muted">
              {num(modelo.mae_por_h[0])} a un mes · {num(modelo.mae_por_h[11])} a doce
            </p>
          </div>
        )}
      </div>

      {esAgregado ? (
        <div className="flex flex-col gap-1.5 border-t border-line pt-2.5">
          <p className="text-[11px] text-ink-2 leading-snug">{modelo.nota}</p>
          {/* la comparación entre modelos es el punto, no un detalle: a doce
              meses el baseline gana, y quien mire un solo modelo no lo vería */}
          <ErrorPorHorizonte modelos={datos.modelos} activo={modeloKey} />
          <p className="text-[11px] text-ink-muted leading-snug">
            {datos.backtest.n_origenes} orígenes de backtest ({datos.backtest.desde.slice(0, 7)} a{" "}
            {datos.backtest.hasta.slice(0, 7)}), reentrenando en cada uno. En 2025, el año del
            quiebre, este modelo erró <span className="tabular">{num(modelo.mae_quiebre)}</span> por
            mes y sobreestimó <span className="tabular">{num(Math.abs(modelo.sesgo_quiebre))}</span>:
            un cambio de nivel que no está en los datos previos no lo anticipa ningún método.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5 border-t border-line pt-2.5">
          <p className="text-[11px] text-ink-2 leading-snug">
            {tipoInfo(tipo).label} con <strong>{elegido.label}</strong>, el modelo elegido. La
            apertura por tipo corre solo con ese: son seis series más cortas y comparar cuatro
            modelos en cada una no cambiaría la lectura.
          </p>
          {pocosCasos ? (
            <p className="text-[11px] text-ink-muted leading-snug">
              Con {num(mensual * 12)} casos proyectados en el año, la variación no se puede leer
              como una tendencia: la banda es más ancha que el propio pronóstico y el signo se da
              vuelta con dos o tres hechos.
            </p>
          ) : (
            <p className="text-[11px] text-ink-muted leading-snug">
              El quiebre de 2025 empujó a lesiones y amenazas en rampa y a robo y hurto de golpe,
              y esta proyección continúa ese movimiento — cuyo origen quedó en duda. Vale para
              dimensionar, no como señal de que el fenómeno se mueve en esa dirección.
            </p>
          )}
        </div>
      )}

      <p className="text-[11px] text-ink-muted leading-snug border-t border-line pt-2.5">
        {datos.salvedad}
      </p>
    </section>
  );
}

/* ------------------------------------------------------------------ la curva */

function Curva({
  historia, proy, base, anio, etiquetaTipo,
}: {
  historia: { anio: number; mes: number; n: number }[];
  proy: MesPronostico[]; base: number; anio: number; etiquetaTipo: string;
}) {
  const w = 420, h = 200;
  const n = historia.length + proy.length;
  const paso = (w - M.izq - M.der) / n;
  const x = (i: number) => M.izq + (i + 0.5) * paso;

  /* Eje desde cero y no recortado al rango de los datos. Un eje truncado
     convertiría una variación del 1,1% en una pendiente dramática, que es
     exactamente la lectura que el README dice que no hay que hacer. */
  const max = Math.max(...historia.map((f) => f.n), ...proy.map((p) => p.hi)) * 1.1 || 1;
  const y = (v: number) => M.arr + (1 - v / max) * (h - M.arr - M.aba);

  const puntosHist = historia.map((f, i) => [x(i), y(f.n)] as const);
  const puntosProy = proy.map((p, i) => [x(historia.length + i), y(p.yhat)] as const);
  const linea = (pts: readonly (readonly [number, number])[]) =>
    "M" + pts.map(([px, py]) => `${px.toFixed(1)},${py.toFixed(1)}`).join(" L");

  /* El pronóstico arranca en el último punto observado: sin ese empalme la
     línea aparece flotando y se lee como si hubiera un salto en enero. */
  const empalme = [puntosHist[puntosHist.length - 1], ...puntosProy] as const;

  const cinta =
    "M" + proy.map((p, i) => `${x(historia.length + i).toFixed(1)},${y(p.hi).toFixed(1)}`).join(" L") +
    " L" + [...proy].reverse().map((p, i) =>
      `${x(historia.length + proy.length - 1 - i).toFixed(1)},${y(p.lo).toFixed(1)}`).join(" L") + " Z";

  const corte = M.izq + historia.length * paso;
  const anios = [...new Set(historia.map((f) => f.anio))];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto" role="img"
         aria-label={
           `Serie mensual de ${etiquetaTipo} en los últimos ${historia.length} meses y ` +
           `pronóstico de los doce meses de ${anio}: ${num(proy[0].yhat)} en enero, ` +
           `entre ${num(proy[0].lo)} y ${num(proy[0].hi)} con 90% de confianza. ` +
           `El promedio mensual del año anterior fue ${num(base)}.`}>
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={M.izq} y1={y(max * f)} x2={w - M.der} y2={y(max * f)}
                stroke="var(--border)" strokeWidth="1" />
          <text x={M.izq - 7} y={y(max * f) + 3.5} textAnchor="end" fontSize="10"
                fill="var(--text-muted)" className="tabular">{num(max * f)}</text>
        </g>
      ))}

      {/* referencia: el promedio mensual del último año cerrado */}
      <line x1={M.izq} y1={y(base)} x2={w - M.der} y2={y(base)}
            stroke="var(--accent)" strokeWidth="1.5" strokeDasharray="4 3" />
      {/* la etiqueta va a la izquierda, sobre la historia: pegada al borde
          derecho caía justo encima de la banda del pronóstico */}
      <text x={M.izq + 3} y={y(base) - 5} textAnchor="start" fontSize="9.5"
            fill="var(--accent)" className="tabular">
        promedio {anio - 1}: {num(base)}
      </text>

      <path d={cinta} fill="var(--brand-wash)" />
      <path d={linea(puntosHist)} fill="none" stroke="var(--brand)" strokeWidth="1.8"
            strokeLinejoin="round" strokeLinecap="round" />
      <path d={linea(empalme)} fill="none" stroke="var(--brand)" strokeWidth="1.8"
            strokeDasharray="4 3" strokeLinejoin="round" strokeLinecap="round" opacity="0.85" />

      <line x1={corte} y1={M.arr} x2={corte} y2={h - M.aba}
            stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3 2" />

      {historia.map((f, i) => (
        <g key={`h${i}`}>
          <circle cx={x(i)} cy={y(f.n)} r="1.6" fill="var(--brand)" opacity="0.7" />
          <rect x={x(i) - paso / 2} y={M.arr} width={paso} height={h - M.arr - M.aba} fill="transparent">
            <title>{`${MESES[f.mes - 1]} ${f.anio}: ${num(f.n)} ${etiquetaTipo} registrados`}</title>
          </rect>
        </g>
      ))}
      {proy.map((p, i) => (
        <g key={`p${i}`}>
          <circle cx={x(historia.length + i)} cy={y(p.yhat)} r="2.2" fill="var(--brand)"
                  stroke="var(--surface-2)" strokeWidth="1" />
          <rect x={x(historia.length + i) - paso / 2} y={M.arr} width={paso}
                height={h - M.arr - M.aba} fill="transparent">
            <title>{`${MESES[p.mes - 1]} ${anio}: ${num(p.yhat)} ${etiquetaTipo} pronosticados ` +
                    `(entre ${num(p.lo)} y ${num(p.hi)})`}</title>
          </rect>
        </g>
      ))}

      {anios.map((a) => {
        const idx = historia.findIndex((f) => f.anio === a);
        const cuantos = historia.filter((f) => f.anio === a).length;
        return (
          <text key={a} x={x(idx) + (cuantos - 1) * paso / 2} y={h - 14} textAnchor="middle"
                fontSize="10" fill="var(--text-muted)">{a}</text>
        );
      })}
      <text x={corte + 6 * paso} y={h - 14} textAnchor="middle" fontSize="10" fill="var(--brand)">
        {anio}
      </text>
      <text x={(M.izq + w - M.der) / 2} y={h - 2} textAnchor="middle" fontSize="9.5"
            fill="var(--text-muted)">
        línea llena, registrado · punteada y con banda, pronóstico
      </text>
    </svg>
  );
}

/* --------------------------------------------- error según cuán lejos se mira */

/* Cuatro modelos × cuatro horizontes, como tabla y no como cuatro líneas: las
   curvas de MAE se cruzan y quedan a menos de 200 delitos entre sí, así que en
   420 px de ancho se superponen y la etiqueta de cada una tapa a la siguiente.
   Lo único que hay que poder leer acá es que el ganador cambia con el horizonte
   —Holt-Winters a un mes, Prophet con regímenes en el medio, el baseline a
   doce— y en una tabla con el mínimo de cada columna marcado eso se ve de una. */

const HORIZONTES = [1, 3, 6, 12];

function ErrorPorHorizonte({
  modelos, activo,
}: { modelos: DatosPronostico["modelos"]; activo: string }) {
  const mejor = HORIZONTES.map((hh) =>
    Math.min(...modelos.map((m) => m.mae_por_h[hh - 1])));

  return (
    <div className="flex flex-col gap-1">
      <p className="text-[11px] text-ink-2">
        Error típico según cuán lejos se mire, en delitos por mes
      </p>
      <table className="w-full text-[10.5px] border-collapse">
        <thead>
          <tr className="text-ink-muted">
            <th scope="col" className="text-left font-normal pb-1">Modelo</th>
            {HORIZONTES.map((hh) => (
              <th key={hh} scope="col" className="text-right font-normal pb-1 tabular">
                {hh === 1 ? "1 mes" : `${hh}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {modelos.map((m) => (
            <tr key={m.key} className={m.key === activo ? "text-ink-2" : "text-ink-muted"}>
              <th scope="row" className={`text-left font-normal py-[1px] pr-2 truncate ${
                m.key === activo ? "text-brand font-semibold" : ""}`}>
                {m.label}
              </th>
              {HORIZONTES.map((hh, i) => {
                const v = m.mae_por_h[hh - 1];
                const esMejor = v === mejor[i];
                return (
                  <td key={hh} className={`text-right tabular py-[1px] ${
                    esMejor ? "text-brand font-semibold" : ""}`}
                      title={esMejor ? `El más preciso a ${hh} ${hh === 1 ? "mes" : "meses"}` : undefined}>
                    {num(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[10.5px] text-ink-muted leading-snug">
        En azul, el más preciso de cada columna. A doce meses no hay nada que le gane a
        repetir el mismo mes del año pasado.
      </p>
    </div>
  );
}
