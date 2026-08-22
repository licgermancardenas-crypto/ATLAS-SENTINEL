"use client";

import { useCallback, useEffect, useState } from "react";
import type { Capa, DatosDashboard, Superficie, TipoDelito, Turno } from "./types";
import { CAPAS, SUPERFICIES, TIPOS, TURNOS } from "./types";
import { cargarDatos } from "./data";

/* La selección y la carga de datos, compartidas por el tablero y por el mapa
   a pantalla completa.

   Estaban dentro de `Dashboard.tsx` y ahí funcionaban, pero apenas hubo una
   segunda página que muestra el mismo mapa con los mismos filtros, dejar dos
   copias del estado y de la sincronización con la URL era garantizar que un
   día se separaran: alguien agrega un filtro en una y no en la otra, o cambia
   un default y los links dejan de significar lo mismo.

   Vive en la query string por dos razones que ya estaban documentadas y siguen
   valiendo: se le puede mandar a alguien el tablero ya filtrado ("mirá hurto
   en la Comuna 1") y se puede capturar o revisar sin manejar el navegador a
   mano. Ahora suma una tercera: **es lo que hace que saltar entre el tablero y
   el mapa conserve lo que uno estaba mirando.** */

function leerURL<T extends string>(clave: string, validos: readonly T[], porDefecto: T): T {
  if (typeof window === "undefined") return porDefecto;
  const v = new URLSearchParams(window.location.search).get(clave);
  return validos.includes(v as T) ? (v as T) : porDefecto;
}

function leerNum(clave: string, porDefecto: number | null): number | null {
  if (typeof window === "undefined") return porDefecto;
  const v = new URLSearchParams(window.location.search).get(clave);
  if (v === null) return porDefecto;
  const n = Number(v);
  return Number.isFinite(n) ? n : porDefecto;
}

export type Tema = "light" | "dark";

export function useSeleccion() {
  const [datos, setDatos] = useState<DatosDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [turno, setTurno] = useState<Turno>(
    () => leerURL("turno", TURNOS.map((t) => t.key), "tarde"));
  const [comuna, setComuna] = useState<number | null>(() => leerNum("comuna", null));
  const [capa, setCapa] = useState<Capa>(
    () => leerURL("capa", CAPAS.map((c) => c.key), "patrullas"));
  const [superficie, setSuperficie] = useState<Superficie>(
    () => leerURL("superficie", SUPERFICIES.map((s) => s.key), "riesgo"));
  const [tipo, setTipo] = useState<TipoDelito>(
    () => leerURL("tipo", TIPOS.map((t) => t.key), "todos"));
  const [kPatrullas, setKPatrullas] = useState(() => leerNum("k", 75) ?? 75);
  const [barrio, setBarrio] = useState<string | null>(
    () => (typeof window === "undefined"
      ? null : new URLSearchParams(window.location.search).get("barrio")));
  const [tema, setTema] = useState<Tema>(
    () => leerURL("tema", ["light", "dark"] as const, "light"));

  useEffect(() => {
    cargarDatos().then(setDatos).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", tema);
  }, [tema]);

  // solo se escriben los valores que no son el default: una URL con siete
  // parámetros siempre puestos es ilegible y no se puede compartir a mano
  const query = new URLSearchParams();
  if (turno !== "tarde") query.set("turno", turno);
  if (tipo !== "todos") query.set("tipo", tipo);
  if (comuna !== null) query.set("comuna", String(comuna));
  if (barrio) query.set("barrio", barrio);
  if (capa !== "patrullas") query.set("capa", capa);
  if (superficie !== "riesgo") query.set("superficie", superficie);
  if (kPatrullas !== 75) query.set("k", String(kPatrullas));
  if (tema !== "light") query.set("tema", tema);
  const qs = query.toString();

  useEffect(() => {
    // replaceState y no push: el botón de atrás no se puede llenar de una
    // entrada por cada clic en un filtro
    window.history.replaceState(null, "", qs ? `?${qs}` : window.location.pathname);
  }, [qs]);

  /* Al elegir un barrio conviene fijar también su comuna: si no, el mapa
     resalta un polígono y la tabla sigue mostrando los otros 47. Va en el
     handler y no en un efecto: derivarlo después del render hace que el
     tablero se pinte una vez con la selección a medias. */
  const elegirBarrio = useCallback((nombre: string | null) => {
    setBarrio(nombre);
    if (!nombre || !datos) return;
    const b = datos.barrios.features.find((f) => f.properties.nombre === nombre);
    if (b?.properties.comuna != null) setComuna(b.properties.comuna);
  }, [datos]);

  const elegirComuna = useCallback((c: number | null) => {
    setComuna(c);
    setBarrio(null);
  }, []);

  const alternarTema = useCallback(() => {
    setTema((t) => (t === "light" ? "dark" : "light"));
  }, []);

  return {
    datos, error,
    turno, setTurno,
    tipo, setTipo,
    comuna, elegirComuna, setComuna,
    barrio, elegirBarrio,
    capa, setCapa,
    superficie, setSuperficie,
    kPatrullas, setKPatrullas,
    tema, alternarTema,
    /** La query string vigente, para que los links entre páginas no pierdan la selección. */
    qs,
  };
}
