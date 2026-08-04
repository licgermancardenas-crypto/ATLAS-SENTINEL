import type { FeatureCollection } from "geojson";
import type { ModuloA, ModuloB, ModuloC, Metricas } from "./types";

async function cargarJSON<T>(ruta: string): Promise<T> {
  const res = await fetch(ruta);
  if (!res.ok) throw new Error(`No se pudo cargar ${ruta}: ${res.status}`);
  return res.json();
}

export interface DatosDashboard {
  hexRiesgo: FeatureCollection;
  moduloA: ModuloA[];
  moduloB: ModuloB[];
  moduloC: ModuloC[];
  comisarias: FeatureCollection;
  camaras: FeatureCollection;
  metricas: Metricas;
}

export async function cargarDatosDashboard(): Promise<DatosDashboard> {
  const [hexRiesgo, moduloA, moduloB, moduloC, comisarias, camaras, metricas] = await Promise.all([
    cargarJSON<FeatureCollection>("/data/hex_riesgo.geojson"),
    cargarJSON<ModuloA[]>("/data/modulo_a.json"),
    cargarJSON<ModuloB[]>("/data/modulo_b.json"),
    cargarJSON<ModuloC[]>("/data/modulo_c.json"),
    cargarJSON<FeatureCollection>("/data/comisarias.geojson"),
    cargarJSON<FeatureCollection>("/data/camaras.geojson"),
    cargarJSON<Metricas>("/data/metricas.json"),
  ]);
  return { hexRiesgo, moduloA, moduloB, moduloC, comisarias, camaras, metricas };
}

export function moduloAaGeojson(datos: ModuloA[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: datos.map((d) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [d.lon, d.lat] },
      properties: { ...d },
    })),
  };
}

export function moduloBaGeojson(datos: ModuloB[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: datos.map((d) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [d.lon, d.lat] },
      properties: { ...d },
    })),
  };
}
