import type { FeatureCollection } from "geojson";
import type {
  BarriosGeoJSON, ComunaResumen, CurvaK, DatosDashboard, FilaSerie,
  PuntoModuloA, PuntoModuloB, PuntoModuloC, Resumen, SensibilidadRadio,
} from "./types";

async function traer<T>(ruta: string): Promise<T> {
  const res = await fetch(ruta, { cache: "force-cache" });
  if (!res.ok) throw new Error(`No se pudo cargar ${ruta} (HTTP ${res.status})`);
  return res.json() as Promise<T>;
}

/** Todo el tablero se sirve de archivos estáticos: no hay backend ni base. Es
 *  suficiente porque el modelo se reentrena por lote, no en vivo. */
export async function cargarDatos(): Promise<DatosDashboard> {
  const [
    barrios, comunas, moduloA, moduloB, moduloC,
    comisarias, camaras, curvaK, radio, serie, resumen,
  ] = await Promise.all([
    traer<BarriosGeoJSON>("/data/barrios_riesgo.geojson"),
    traer<ComunaResumen[]>("/data/comunas_resumen.json"),
    traer<PuntoModuloA[]>("/data/modulo_a_k75.json"),
    traer<PuntoModuloB[]>("/data/modulo_b_red.json"),
    traer<PuntoModuloC[]>("/data/modulo_c.json"),
    traer<FeatureCollection>("/data/comisarias.geojson"),
    traer<FeatureCollection>("/data/camaras.geojson"),
    traer<CurvaK>("/data/curva_k.json"),
    traer<SensibilidadRadio>("/data/sensibilidad_radio.json"),
    traer<FilaSerie[]>("/data/serie_delitos.json"),
    traer<Resumen>("/data/resumen.json"),
  ]);
  return { barrios, comunas, moduloA, moduloB, moduloC, comisarias, camaras, curvaK, radio, serie, resumen };
}
