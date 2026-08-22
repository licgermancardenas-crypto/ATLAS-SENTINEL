"use client";

import type { Capa, Superficie, TipoDelito } from "@/lib/types";
import { esDemografica, superficieInfo, tipoInfo } from "@/lib/types";
import { ETIQUETAS_CLASE, VAR_EDAD, VAR_RIESGO } from "@/lib/escala";
import { num, num1, num3 } from "@/lib/formato";

/* Los accesorios del mapa: leyenda de la escala, aviso de qué NO cambia con
   los filtros, y leyenda de los puntos de la capa operativa.

   Viven acá y no dentro del tablero porque el mapa ahora tiene dos casas —el
   panel del tablero y la página a pantalla completa— y estas tres piezas
   tienen que decir exactamente lo mismo en las dos. Duplicarlas era duplicar
   las advertencias, que es justo lo que no puede pasar: son el lugar donde el
   tablero avisa que el filtro de turno no toca un mapa demográfico. */

/* La rampa de la edad es azul y la del riesgo ámbar, y no es decoración: con
   la misma rampa, un mapa de "% de mayores de 65" sale del color del peligro y
   se lee como uno. Los cortes son quintiles en los dos casos, pero sobre
   conjuntos distintos — 48 barrios o 15 comunas. */
export function Leyenda({
  cortes, demografica, formato,
}: { cortes: number[]; demografica: boolean; formato: "riesgo" | "pct" | "entero" }) {
  const vars = demografica ? VAR_EDAD : VAR_RIESGO;
  const fmt = (v: number) =>
    formato === "pct" ? `${num1(v)}%` : formato === "entero" ? num(v) : num3(v);
  return (
    <div className="flex items-center gap-2 shrink-0">
      <span className="text-[10px] text-ink-muted">{demografica ? "menos" : "bajo"}</span>
      <div className="flex" role="img"
           aria-label={`Escala de ${demografica ? "edad" : "riesgo"} en cinco grupos con la misma `
                       + `cantidad de barrios cada uno`}>
        {/* borde hairline en cada muestra: la clase más baja de las dos rampas
            está a 1,1:1 del fondo de la tarjeta —medido— y sin delimitar se lee
            como un hueco en la leyenda. En el mapa la clase clara se deja como
            está: ahí abajo hay basemap, no una superficie blanca. */}
        {vars.map((v, i) => (
          <span key={v} className="w-6 h-3 first:rounded-l-sm last:rounded-r-sm border border-line"
                style={{ background: `var(${v})` }}
                title={`${ETIQUETAS_CLASE[i]}${cortes[i] !== undefined ? ` · hasta ${fmt(cortes[i])}` : ""}`} />
        ))}
      </div>
      <span className="text-[10px] text-ink-muted">{demografica ? "más" : "alto"}</span>
    </div>
  );
}

/* Las dos cosas que el filtro por tipo NO cambia, dichas donde se las puede
   leer mal. Sin esto, alguien filtra por hurto, ve moverse la coropleta y las
   patrullas quietas, y concluye que ese es el plan óptimo para hurto — cuando
   los Módulos A/B/C se resuelven sobre el modelo agregado. El README lo tiene
   medido: hurto y lesiones comparten solo el 60% de las ubicaciones. */

export function AvisoSuperficie({
  tipo, capa, superficie,
}: { tipo: TipoDelito; capa: Capa; superficie: Superficie }) {
  /* Con una superficie demográfica el mapa deja de responder al turno y al
     tipo, que siguen puestos arriba y siguen filtrando el resto del tablero.
     Sin este cartel, mover el turno y ver el mapa quieto se lee como un bug. */
  if (esDemografica(superficie)) {
    const info = superficieInfo(superficie);
    return (
      <Aviso>
        El mapa dibuja demografía por {info.unidad}: no cambia con el turno ni con el tipo de
        delito, que siguen filtrando el resto del tablero.{" "}
        {superficie === "hacinamiento"
          ? "Hacinamiento crítico es más de 3 personas por cuarto. No está publicado por radio censal, así que no se puede bajar a barrio. En la auditoría de equidad es la única variable que cambia de signo al controlar por historial delictivo — anotada como señal a vigilar, no como hallazgo: con 15 comunas no alcanza para concluir."
          : info.unidad === "comuna"
          ? "El Censo 2022 no está publicado por barrio."
          : superficie === "nbi"
          ? "NBI mide pobreza estructural del Censo 2010, sobre hogares y no sobre personas. Y no es un mapa de riesgo: la correlación entre NBI y riesgo predicho por comuna cae de 0,41 a 0,14 al controlar por historial delictivo."
          : "La densidad divide la población del Censo 2010 por la superficie del polígono."}
      </Aviso>
    );
  }
  if (tipo === "todos") return null;
  const info = tipoInfo(tipo);
  const mensaje = !info.superficie
    ? `${info.label}: los delitos del tablero son de este tipo, pero el mapa dibuja el riesgo agregado. ${info.nota}`
    : capa !== "ninguna"
    ? `El mapa muestra la superficie de ${info.label.toLowerCase()}, pero las ubicaciones propuestas se optimizan sobre el modelo agregado — no son el plan óptimo para ${info.label.toLowerCase()}.`
    : null;
  if (!mensaje) return null;
  return <Aviso>{mensaje}</Aviso>;
}

function Aviso({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3 py-1.5 border-t border-line text-[11px] leading-snug text-ink-2
                  flex items-start gap-1.5 bg-[var(--warn-wash,transparent)]">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--warn)" strokeWidth="2.2"
           strokeLinecap="round" strokeLinejoin="round" className="shrink-0 mt-[2px]" aria-hidden="true">
        <circle cx="12" cy="12" r="10" /><path d="M12 8v5M12 16h.01" />
      </svg>
      <span>{children}</span>
    </p>
  );
}

export function LeyendaPuntos({ capa, k }: { capa: Capa; k: number }) {
  const items =
    capa === "patrullas"
      ? [{ c: "var(--pt-existente)", t: "Comisarías actuales (75)" },
         { c: "var(--pt-propuesto)", t: `Patrullas propuestas (${k})` }]
      : capa === "camaras"
      ? [{ c: "var(--pt-existente)", t: "Cámaras existentes (224)" },
         { c: "var(--pt-propuesto)", t: "Cámaras propuestas (30)" }]
      : [{ c: "var(--pt-alerta)", t: "Accesos rankeados (9) — el tamaño es el puesto" }];
  return (
    <div className="px-3 py-1.5 border-t border-line flex items-center gap-4 flex-wrap">
      {items.map((i) => (
        <span key={i.t} className="inline-flex items-center gap-1.5 text-[11px] text-ink-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: i.c }} />
          {i.t}
        </span>
      ))}
    </div>
  );
}
