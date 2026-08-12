/**
 * Geometría del mapa ya proyectada a coordenadas SVG.
 * La genera src/export/generar_mapa_svg.py a partir de los barrios reales,
 * el grafo vial de OSM y hex_riesgo.geojson.
 */

export interface ProyeccionMapa {
  /** origen mercator en x, borde superior en y, escala y padding del lienzo */
  x0: number;
  y1: number;
  esc: number;
  pad: number;
  w: number;
  h: number;
}

export interface HexMapa {
  id: string;
  /** path SVG del hexágono, ya proyectado */
  d: string;
  barrio: string | null;
  comuna: number | null;
  manana: number;
  tarde: number;
  noche: number;
  madrugada: number;
}

export interface MapaBase {
  proyeccion: ProyeccionMapa;
  tierra: string;
  barrios: string;
  vias: { menor: string; media: string; troncal: string };
  hex: HexMapa[];
}

/** Misma Web Mercator que usó el generador, para ubicar puntos sueltos
 *  (comisarías, cámaras, patrullas) sobre el mismo lienzo. */
export function proyectar(p: ProyeccionMapa, lon: number, lat: number): { x: number; y: number } {
  const x = (lon * Math.PI) / 180;
  const y = Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
  return { x: (x - p.x0) * p.esc + p.pad, y: (p.y1 - y) * p.esc + p.pad };
}

export async function cargarMapaBase(): Promise<MapaBase> {
  const res = await fetch("/data/mapa_base.json");
  if (!res.ok) throw new Error(`No se pudo cargar el mapa base: ${res.status}`);
  return res.json();
}
