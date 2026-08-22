"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import type { BarrioProps } from "@/lib/types";
import { claveDelitos, claveRiesgo, esDemografica, riesgoEsDelTipo,
         superficieInfo, tasaInflada, tipoInfo } from "@/lib/types";
import { cortesPorCuantil } from "@/lib/escala";
import { num, pct, tasa100k } from "@/lib/formato";
import { useSeleccion } from "@/lib/useSeleccion";
import {
  ChipsActivos, ControlK, SelectorCapa, SelectorComuna, SelectorSuperficie,
  SelectorTipo, SelectorTurno, ToggleTema,
} from "./Controles";
import { AvisoSuperficie, Leyenda, LeyendaPuntos } from "./MapaChrome";

const Mapa = dynamic(() => import("./Mapa"), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full grid place-items-center bg-surface-sunk">
      <span className="text-xs text-ink-muted">Cargando mapa…</span>
    </div>
  ),
});

/* El mapa a pantalla completa.

   En el tablero el mapa comparte la fila con otro panel y vive en una tarjeta
   de alto acotado, porque ahí compite con doce paneles más. Cuando lo que uno
   quiere es leer el territorio —seguir un corredor, comparar dos comunas
   vecinas, mirar dónde caen las patrullas— ese recorte molesta.

   Acá el mapa va a sangre y los controles flotan encima, en vez de ocupar una
   columna fija: una barra lateral de 300 px se come un sexto de la pantalla
   incluso cuando no se la está mirando. Los dos paneles se pliegan, así que el
   piso es el mapa entero.

   **Comparte estado con el tablero por la query string**, así que saltar de una
   página a la otra conserva turno, tipo, comuna, barrio, capa, superficie, K y
   tema. Es la misma selección vista de dos maneras, no dos tableros. */

export default function MapaPantalla() {
  const [panel, setPanel] = useState(true);
  const {
    datos, error, turno, setTurno, tipo, setTipo, comuna, elegirComuna,
    barrio, elegirBarrio, capa, setCapa, superficie, setSuperficie,
    kPatrullas, setKPatrullas, tema, alternarTema, qs,
  } = useSeleccion();

  if (error) {
    return (
      <main className="h-full grid place-items-center p-6">
        <div className="card p-5 max-w-md flex flex-col gap-2">
          <h1 className="text-sm font-semibold text-[var(--bad)]">No se pudieron cargar los datos</h1>
          <p className="text-xs text-ink-2">{error}</p>
          <Link href="/" className="mt-2 self-start px-3 py-1.5 text-xs rounded bg-brand text-white">
            Volver al tablero
          </Link>
        </div>
      </main>
    );
  }

  if (!datos) {
    return (
      <main className="h-full grid place-items-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-1 w-40 bg-surface-sunk rounded overflow-hidden">
            <div className="h-full w-1/3 bg-brand animate-pulse" />
          </div>
          <span className="text-xs text-ink-muted">Cargando el mapa…</span>
        </div>
      </main>
    );
  }

  const props: BarrioProps[] = datos.barrios.features.map((f) => f.properties);
  const ks = datos.curvaK.curva.filter((p) => p.cobertura !== null).map((p) => p.k);
  const supInfo = superficieInfo(superficie);
  const demografica = esDemografica(superficie);
  const clave = claveRiesgo(turno, tipo);
  const claveD = claveDelitos(tipo);

  const cortes = supInfo.unidad === "comuna"
    ? cortesPorCuantil(datos.comunasGeo.features.map((f) => f.properties[supInfo.campo!] ?? NaN))
    : superficie === "densidad" || superficie === "nbi"
    ? cortesPorCuantil(datos.demografia.barrios.map(
        (b) => (b[supInfo.campo as "densidad" | "pct_nbi"] as number | null) ?? NaN))
    : cortesPorCuantil(props.map((b) => b[clave] as number));

  // el ámbito que están mirando: barrio si hay, si no comuna, si no la Ciudad
  const foco = barrio ? props.filter((b) => b.nombre === barrio)
    : comuna === null ? props : props.filter((b) => b.comuna === comuna);
  const ambito = barrio ?? (comuna === null ? "toda la Ciudad" : `Comuna ${comuna}`);
  const delitos = foco.reduce((s, b) => s + (b[claveD] as number), 0);
  const poblacion = foco.reduce((s, b) => s + ((b.poblacion as number) ?? 0), 0);
  const tasa = tasa100k(delitos, poblacion);
  const inflada = foco.length < props.length
    && foco.some((b) => tasaInflada(b.presion_visitantes as number | null));
  const cob = datos.curvaK.curva.find((p) => p.k === kPatrullas)?.cobertura ?? null;

  return (
    <main className="h-full relative overflow-hidden">
      {/* el mapa a sangre: es la capa de abajo y ocupa todo */}
      <div className="absolute inset-0">
        <Mapa
          datos={datos} turno={turno} capa={capa} superficie={superficie} tipo={tipo}
          comuna={comuna} barrioActivo={barrio} kPatrullas={kPatrullas} tema={tema}
          onBarrio={elegirBarrio}
        />
      </div>

      {/* barra superior: identidad y salidas. Delgada a propósito — cada píxel
          que ocupa es mapa que no se ve. */}
      <div className="absolute top-0 inset-x-0 z-[1000] flex items-center gap-3 px-3 py-2
                      bg-surface-2/92 backdrop-blur border-b border-line">
        <h1 className="text-[13px] font-semibold tracking-tight whitespace-nowrap">
          ATLAS SENTINEL <span className="text-ink-muted font-normal">· Mapa</span>
        </h1>
        <span className="text-[11px] text-ink-muted truncate hidden md:block">
          {demografica ? supInfo.descripcion
            : riesgoEsDelTipo(tipo) ? `Riesgo de ${tipoInfo(tipo).label.toLowerCase()} por barrio`
            : "Riesgo por barrio"}
        </span>
        <div className="ml-auto flex items-center gap-2 shrink-0">
          <ChipsActivos
            comuna={comuna} barrio={barrio} tipo={tipo}
            onLimpiarComuna={() => elegirComuna(null)}
            onLimpiarBarrio={() => elegirBarrio(null)}
            onLimpiarTipo={() => setTipo("todos")}
          />
          {/* los links conservan la selección: es la misma vista, no otro tablero */}
          <Link href={`/${qs ? `?${qs}` : ""}`}
                className="rounded border border-line bg-surface-1 px-2.5 py-1 text-[11px]
                           hover:bg-surface-sunk whitespace-nowrap">
            ← Tablero
          </Link>
          <Link href="/3d"
                className="rounded border border-line bg-surface-1 px-2.5 py-1 text-[11px]
                           hover:bg-surface-sunk whitespace-nowrap">
            Ver en 3D
          </Link>
          <ToggleTema tema={tema} onChange={alternarTema} />
        </div>
      </div>

      {/* panel de filtros, plegable */}
      <div className="absolute top-14 left-3 z-[1000] w-[17.5rem] max-w-[calc(100vw-1.5rem)]
                      flex flex-col gap-2">
        <button
          onClick={() => setPanel((v) => !v)}
          aria-expanded={panel}
          className="self-start rounded border border-line bg-surface-2/95 backdrop-blur px-2.5 py-1
                     text-[11px] text-ink-2 hover:bg-surface-sunk cursor-pointer shadow-[var(--shadow-card)]"
        >
          {panel ? "Ocultar filtros" : "Filtros"}
        </button>

        {panel && (
          <div className="card bg-surface-2/95 backdrop-blur p-3 flex flex-col gap-3
                          max-h-[calc(100vh-13rem)] overflow-y-auto overflow-x-hidden
                          scroll-fino">
            <SelectorTurno valor={turno} onChange={setTurno} />
            <SelectorTipo valor={tipo} onChange={setTipo} />
            <SelectorComuna valor={comuna} onChange={elegirComuna} comunas={datos.comunas} />
            <SelectorSuperficie valor={superficie} onChange={setSuperficie} />
            <SelectorCapa valor={capa} onChange={setCapa} />
            {capa === "patrullas" && (
              <ControlK valor={kPatrullas} onChange={setKPatrullas} disponibles={ks} />
            )}
            <div className="border-t border-line pt-2 flex flex-col gap-1.5">
              <span className="text-[10px] uppercase tracking-[0.08em] text-ink-muted font-medium">
                Escala
              </span>
              <Leyenda cortes={cortes} demografica={demografica} formato={supInfo.formato} />
            </div>
          </div>
        )}
      </div>

      {/* las tarjetas del ámbito elegido, abajo a la izquierda: es lo que
          contesta "¿y esto que estoy mirando cuánto es?" sin volver al tablero */}
      {/* cuando el panel esta abierto las tarjetas arrancan a su derecha; con
          el panel plegado usan el ancho completo. Antes se superponian y el
          panel quedaba cortado por abajo. */}
      <div className={`absolute bottom-3 right-3 z-[1000] flex items-end gap-2 flex-wrap
                       pointer-events-none transition-[left] duration-200 ${
        panel ? "left-[19.5rem]" : "left-3"}`}>
        <div className="flex gap-2 flex-wrap pointer-events-auto">
          <Tarjeta etiqueta={barrio ? "Barrio" : comuna !== null ? "Comuna" : "Ciudad"}
                   valor={ambito} chico />
          <Tarjeta etiqueta={tipo === "todos" ? "Delitos 2025" : `${tipoInfo(tipo).label} 2025`}
                   valor={num(delitos)} />
          <Tarjeta etiqueta="Cada 100.000 hab."
                   valor={tasa === null ? "—" : num(tasa)}
                   nota={tasa === null ? "sin población"
                     : inflada ? "sobreestimada · mucha gente de afuera"
                     : `${num(poblacion)} habitantes`}
                   alerta={inflada} />
          {capa === "patrullas" && (
            <Tarjeta etiqueta={`Cobertura con ${kPatrullas}`}
                     valor={cob === null ? "—" : pct(cob)}
                     nota={`hoy ${pct(datos.curvaK.cobertura_actual)} con ${datos.curvaK.n_comisarias} comisarías`} />
          )}
        </div>
      </div>

      {/* los mismos avisos que en el tablero, arriba a la derecha para no tapar
          las tarjetas. Van sí o sí: son el lugar donde se dice que el filtro de
          turno no toca un mapa demográfico. */}
      <div className="absolute top-14 right-3 z-[1000] w-[22rem] max-w-[calc(100vw-1.5rem)]
                      flex flex-col gap-2 pointer-events-none">
        <div className="card bg-surface-2/95 backdrop-blur overflow-hidden pointer-events-auto">
          <AvisoSuperficie tipo={tipo} capa={capa} superficie={superficie} />
          {capa !== "ninguna" && <LeyendaPuntos capa={capa} k={kPatrullas} />}
        </div>
      </div>
    </main>
  );
}

function Tarjeta({
  etiqueta, valor, nota, alerta, chico,
}: { etiqueta: string; valor: string; nota?: string; alerta?: boolean; chico?: boolean }) {
  return (
    <div className="card bg-surface-2/95 backdrop-blur px-3 py-2 flex flex-col gap-0.5 min-w-0">
      <span className="text-[9.5px] uppercase tracking-[0.07em] text-ink-muted leading-tight">
        {etiqueta}
      </span>
      <span className={`${chico ? "text-[13px]" : "text-lg"} font-semibold leading-none truncate
                        ${chico ? "" : "tabular"}`}>
        {valor}
      </span>
      {nota && (
        <span className={`text-[10px] leading-tight ${alerta ? "text-[var(--warn)]" : "text-ink-muted"}`}>
          {nota}
        </span>
      )}
    </div>
  );
}
