"use client";

import type { PerfilTemporal, TipoDelito } from "@/lib/types";
import { tipoInfo, TURNOS_PERFIL } from "@/lib/types";
import { cadaCuanto, num, num1, pct } from "@/lib/formato";

/* "Cuándo ocurren".
 *
 *  Hay una asimetría acá que decide todo el diseño: la CASCADA de frecuencias
 *  se puede calcular para cualquier selección (es el total de la selección
 *  dividido por tiempo), pero los PERFILES —hora del día, día de la semana—
 *  vienen agregados para toda la Ciudad y no por barrio. Mezclarlos sin avisar
 *  haría que alguien filtre por Balvanera, mire el pico de las 18h y crea que
 *  es el pico de Balvanera. Por eso van visualmente separados y el perfil dice
 *  "toda la Ciudad" en su propio encabezado, incluso cuando hay filtro puesto.
 */

const ESCALAS = [
  { etiqueta: "por hora", divisor: (dias: number) => dias * 24 },
  { etiqueta: "por día", divisor: (dias: number) => dias },
  { etiqueta: "por semana", divisor: (dias: number) => dias / 7 },
  { etiqueta: "por mes", divisor: (dias: number) => dias / 30.44 },
];

export default function Cuando({
  perfil, tipo, delitosSeleccion, ambito,
}: {
  perfil: PerfilTemporal;
  tipo: TipoDelito;
  /** Delitos del tipo elegido dentro de la selección activa (comuna/barrio). */
  delitosSeleccion: number;
  /** Cómo se llama esa selección, para poder decirlo en pantalla. */
  ambito: string;
}) {
  const { dias } = perfil;
  const cada = cadaCuanto(delitosSeleccion, dias);
  const uno = tipoInfo(tipo).uno;

  const franja = perfil.franja[tipo] ?? perfil.franja.todos;
  const semana = perfil.dia_semana[tipo] ?? perfil.dia_semana.todos;
  const turnos = perfil.turno[tipo] ?? perfil.turno.todos;
  const totalPerfil = turnos.reduce((a, b) => a + b, 0);

  const horaPico = franja.indexOf(Math.max(...franja));
  const diaPicoIdx = semana.indexOf(Math.max(...semana));
  const diaFlojoIdx = semana.indexOf(Math.min(...semana));
  const turnoPicoIdx = turnos.indexOf(Math.max(...turnos));

  /* Con pocos casos el perfil es ruido y no señal: homicidios son 78 hechos
     repartidos en 7 días y 24 horas, así que el "día pico" cambia de año a año
     por azar. El umbral es deliberadamente grosero — no pretende ser un test,
     solo evitar que el tablero afirme "el sábado es 280% peor que el martes"
     como si fuera un hallazgo. */
  const pocosCasos = totalPerfil < 1000;

  return (
    <section className="card p-3 flex flex-col gap-3">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Cuándo ocurren
        </h2>
        <p className="text-[11px] text-ink-muted">
          Sobre {num(dias)} días de {perfil.anio}.
        </p>
      </div>

      {/* ---------- cascada: sí sigue la selección ---------- */}
      <div className="flex flex-col gap-2">
        <p className="text-[13px] leading-snug">
          <span className="text-ink-2">{uno[0].toUpperCase() + uno.slice(1)} cada </span>
          <strong className="text-[19px] tabular text-brand">{cada.valor}</strong>
          <span className="text-ink-2"> {cada.unidad}</span>
          <span className="text-ink-muted text-[11px]"> · {ambito}</span>
        </p>
        <div className="grid grid-cols-4 gap-px bg-line rounded overflow-hidden">
          {ESCALAS.map((e) => {
            const v = delitosSeleccion / e.divisor(dias);
            return (
              <div key={e.etiqueta} className="bg-surface-2 px-2 py-1.5 text-center">
                <div className="text-[15px] tabular font-semibold leading-tight">
                  {/* "0,0" se lee como un error de carga; con homicidios la
                      frecuencia por hora es real pero cae abajo del redondeo */}
                  {v > 0 && v < 0.05 ? "<0,1" : v >= 100 ? num(v) : num1(v)}
                </div>
                <div className="text-[10px] text-ink-muted whitespace-nowrap">{e.etiqueta}</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ---------- perfiles: NO siguen la selección ---------- */}
      <div className="flex flex-col gap-2.5 border-t border-line pt-2.5">
        <p className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
          Perfil horario · toda la Ciudad
        </p>

        <PerfilHoras franja={franja} total={totalPerfil} pico={horaPico} />

        <p className="text-[11px] text-ink-2 leading-snug">
          {/* el turno agrupa 6-8 horas y aguanta mucho mejor el poco volumen que
              la hora suelta, así que con pocos casos se afirma solo el turno */}
          {!pocosCasos && (
            <>El pico es a las <strong className="tabular">{horaPico}h</strong>. </>
          )}
          El turno más cargado es{" "}
          <strong>{TURNOS_PERFIL[turnoPicoIdx].toLowerCase()}</strong>, con{" "}
          <strong className="tabular">{pct(turnos[turnoPicoIdx] / (totalPerfil || 1))}</strong> del total.
        </p>

        <PerfilSemana semana={semana} dias={perfil.dias_orden} pico={diaPicoIdx} />

        {pocosCasos ? (
          <p className="text-[11px] text-ink-muted leading-snug">
            Con {num(totalPerfil)} casos en el año, el reparto por hora y por día es
            demasiado ruidoso para leerlo como un patrón: el pico cambia de un año a otro por azar.
          </p>
        ) : (
          <p className="text-[11px] text-ink-2 leading-snug">
            El día más cargado es <strong>{perfil.dias_orden[diaPicoIdx].toLowerCase()}</strong>, un{" "}
            <strong className="tabular">
              {num1((semana[diaPicoIdx] / (semana[diaFlojoIdx] || 1) - 1) * 100)}%
            </strong>{" "}
            arriba del {perfil.dias_orden[diaFlojoIdx].toLowerCase()}.
          </p>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ perfil horario */

/* Las 24 barras van con las bandas de turno de fondo: sin eso hay que contar
   posiciones para saber si el pico de las 18h cae en "tarde" o en "noche", que
   es justo la traducción que el resto del tablero usa. */
const BANDAS: { desde: number; hasta: number; nombre: string }[] = [
  { desde: 0, hasta: 6, nombre: "Madrugada" },
  { desde: 6, hasta: 12, nombre: "Mañana" },
  { desde: 12, hasta: 20, nombre: "Tarde" },
  { desde: 20, hasta: 24, nombre: "Noche" },
];

function PerfilHoras({ franja, total, pico }: { franja: number[]; total: number; pico: number }) {
  const w = 420, h = 92, izq = 4, aba = 15;
  const max = Math.max(...franja) || 1;
  const bw = (w - izq * 2) / 24;

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-auto" role="img"
         aria-label={`Perfil horario: el pico es a las ${pico} horas, con ${franja[pico]} hechos.`}>
      {BANDAS.map((b) => (
        <g key={b.nombre}>
          <rect x={izq + b.desde * bw} y={0} width={(b.hasta - b.desde) * bw} height={h - aba}
                fill="var(--surface-sunk)" opacity="0.6" />
          <text x={izq + ((b.desde + b.hasta) / 2) * bw} y={9} textAnchor="middle"
                fontSize="8" fill="var(--text-muted)">{b.nombre}</text>
        </g>
      ))}
      {franja.map((n, i) => {
        const alto = (n / max) * (h - aba - 14);
        const esPico = i === pico;
        return (
          <rect key={i} x={izq + i * bw + 0.8} y={h - aba - alto} width={bw - 1.6} height={alto}
                rx="1" fill={esPico ? "var(--brand)" : "var(--brand-soft)"}>
            <title>{`${String(i).padStart(2, "0")}:00 — ${num(n)} hechos (${pct(n / (total || 1))})`}</title>
          </rect>
        );
      })}
      {[0, 6, 12, 18, 23].map((i) => (
        <text key={i} x={izq + i * bw + bw / 2} y={h - 4} textAnchor="middle" fontSize="8.5"
              fill="var(--text-muted)" className="tabular">{i}</text>
      ))}
    </svg>
  );
}

/* ------------------------------------------------------- perfil de la semana */

function PerfilSemana({
  semana, dias, pico,
}: { semana: number[]; dias: string[]; pico: number }) {
  const max = Math.max(...semana) || 1;
  const min = Math.min(...semana);
  return (
    <div className="flex items-end gap-1 h-14" role="img"
         aria-label={`Por día de la semana, el máximo es ${dias[pico]}.`}>
      {semana.map((n, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1 h-full justify-end">
          <span className="w-full rounded-t-sm transition-all duration-200"
                style={{
                  // la escala arranca en el 85% del mínimo y no en cero: las
                  // diferencias entre días son de ~10% y contra un eje en cero
                  // las siete barras se ven iguales
                  height: `${8 + ((n - min * 0.85) / (max - min * 0.85)) * 78}%`,
                  background: i === pico ? "var(--brand)" : "var(--brand-soft)",
                }}
                title={`${dias[i]}: ${num(n)} hechos`} />
          <span className={`text-[9px] ${i === pico ? "text-brand font-semibold" : "text-ink-muted"}`}>
            {dias[i].slice(0, 3)}
          </span>
        </div>
      ))}
    </div>
  );
}
