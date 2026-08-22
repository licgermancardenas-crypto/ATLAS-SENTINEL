"use client";

import type { Victimas as DatosVictimas } from "@/lib/types";
import { num, num1 } from "@/lib/formato";

/* El único panel del tablero que no es espacial, y va igual.

   Todo lo demás acá contesta *dónde* y *cuánto*. Nada contesta *a quién*,
   porque los 1,35M de delitos georreferenciados no traen un solo atributo del
   damnificado. El SNIC sí registra víctimas, y este panel muestra exactamente
   hasta dónde llega ese registro — que es bastante menos de lo que uno
   esperaría, y esa limitación es la mitad del contenido.

   Tres decisiones, y las tres son sobre qué NO esconder:

   1. **La ausencia va primero.** Robo, hurto y amenazas —que son el grueso
      del tablero— no tienen ni una víctima caracterizada sobre medio millón
      de hechos. Poner las categorías que sí tienen dato arriba y la nota al
      pie dejaría creer que el corte por sexo aplica a todo.
   2. **El "sin dato" es una barra, no un descarte.** Va del 26% al 74% según
      la categoría. Un "51% de las víctimas de lesiones son mujeres" calculado
      sobre los caracterizados es cierto y engañoso a la vez si no se ve que
      cuatro de cada diez casos quedaron afuera.
   3. **No sigue el filtro de tipo.** Las categorías son las del código penal
      que usa el SNIC, no las seis del Mapa del Delito de GCBA. No son
      intercambiables y fingir que lo son sería el error más fácil de cometer. */

export default function Victimas({ datos }: { datos: DatosVictimas }) {
  const sin = datos.sin_caracterizar;
  const maxVictimas = Math.max(...datos.delitos.map((d) => d.victimas));

  return (
    <section className="card p-3 flex flex-col gap-2.5">
      <div>
        <h2 className="text-xs font-semibold uppercase tracking-[0.07em] text-ink-2">
          Quién es la víctima
        </h2>
        <p className="text-[11px] text-ink-muted">
          Toda la Ciudad, {datos.desde}–{datos.hasta} · {datos.fuente}. No sigue el filtro de
          comuna, barrio ni tipo: es la única fuente del tablero que no es espacial.
        </p>
      </div>

      {/* la ausencia primero: es el hallazgo, no una salvedad */}
      <div className="rounded border border-line bg-surface-sunk px-2.5 py-2 flex flex-col gap-1">
        <p className="text-[11px] text-ink-2 leading-snug">
          <strong>Robo, hurto y amenazas no registran ni una víctima.</strong> No es que falten
          algunas: el SNIC solo carga víctimas en delitos contra las personas, así que sobre{" "}
          <span className="tabular">{num(sin.hechos)}</span> hechos de{" "}
          <span className="tabular">{sin.n_categorias}</span> categorías no hay nadie
          caracterizado — y ahí adentro están los dos tipos que dominan el tablero.
        </p>
        <ul className="flex flex-col gap-0.5">
          {sin.principales.map((p) => (
            <li key={p.delito} className="flex justify-between gap-2 text-[10.5px] text-ink-muted">
              <span className="truncate">{p.delito}</span>
              <span className="tabular shrink-0">{num(p.hechos)} hechos</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-1.5">
        <p className="text-[11px] text-ink-2">Donde sí hay dato, por sexo</p>
        <div className="flex gap-3 flex-wrap text-[10px] text-ink-muted">
          <Ref color="var(--serie-1)" texto="varones" />
          <Ref color="var(--serie-2)" texto="mujeres" />
          <Ref color="var(--border-strong)" texto="sin dato" />
        </div>

        <div className="flex flex-col gap-1">
          {datos.delitos.slice(0, 8).map((d) => (
            <Barra key={d.delito} fila={d} max={maxVictimas} />
          ))}
        </div>
      </div>

      <p className="text-[10.5px] text-ink-muted leading-snug border-t border-line pt-2">
        {datos.notas.sin_edad}
      </p>
    </section>
  );
}

function Ref({ color, texto }: { color: string; texto: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="w-2.5 h-2.5 rounded-[2px]" style={{ background: color }} />
      {texto}
    </span>
  );
}

function Barra({
  fila, max,
}: {
  fila: { delito: string; victimas: number; masc: number; fem: number; sd: number };
  max: number;
}) {
  const { masc, fem, sd, victimas } = fila;
  const conocidos = masc + fem;
  // el ancho total codifica el volumen: sin eso, homicidios (339 víctimas) y
  // lesiones (45.435) se verían igual de importantes
  const ancho = (victimas / max) * 100;
  const seg = (v: number) => (v / victimas) * 100;
  const pctFem = conocidos > 0 ? (fem / conocidos) * 100 : null;

  return (
    <div className="flex flex-col gap-[2px]"
         title={`${fila.delito}: ${num(victimas)} víctimas — ${num(masc)} varones, ` +
                `${num(fem)} mujeres, ${num(sd)} sin dato` +
                (pctFem !== null
                  ? `. Entre los caracterizados, ${num1(pctFem)}% son mujeres.` : ".")}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[10.5px] text-ink-2 truncate">{fila.delito}</span>
        <span className="text-[10px] text-ink-muted tabular shrink-0">{num(victimas)}</span>
      </div>
      <div className="h-3 flex rounded-sm overflow-hidden gap-[2px] bg-surface-sunk"
           style={{ width: `${Math.max(ancho, 8)}%` }}>
        <span style={{ width: `${seg(masc)}%`, background: "var(--serie-1)" }} />
        <span style={{ width: `${seg(fem)}%`, background: "var(--serie-2)" }} />
        <span style={{ width: `${seg(sd)}%`, background: "var(--border-strong)" }} />
      </div>
    </div>
  );
}
