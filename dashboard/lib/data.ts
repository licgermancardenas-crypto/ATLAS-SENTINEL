import type { FeatureCollection } from "geojson";
import type {
  BarriosGeoJSON, ComunaResumen, ComunasGeoJSON, CoberturaPoblacion, CurvaK, DatosDashboard,
  Demografia, EquidadCobertura, Victimas,
  FilaSerie, PerfilTemporal,
  Pronostico, PuntoModuloA, PuntoModuloB, PuntoModuloC, Resumen, SensibilidadRadio,
} from "./types";

/* `no-cache` y no `force-cache`: revalida contra el servidor antes de usar la
   copia local. Los archivos tienen nombre fijo, sin hash, así que con
   `force-cache` el navegador se queda con la versión vieja para siempre — cada
   vez que se regenera el export, quien ya había abierto el tablero sigue viendo
   los números anteriores. Pasó de verdad al agregar el filtro por tipo: los
   campos nuevos no estaban en la copia cacheada y el tablero mostraba NaN.
   El costo es una petición condicional por archivo, que si nada cambió termina
   en un 304 sin cuerpo. */
async function traer<T>(ruta: string): Promise<T> {
  const res = await fetch(ruta, { cache: "no-cache" });
  if (!res.ok) throw new Error(`No se pudo cargar ${ruta} (HTTP ${res.status})`);
  return res.json() as Promise<T>;
}

/** Todo el tablero se sirve de archivos estáticos: no hay backend ni base. Es
 *  suficiente porque el modelo se reentrena por lote, no en vivo. */
export async function cargarDatos(): Promise<DatosDashboard> {
  const [
    barrios, comunas, moduloA, moduloB, moduloC,
    comisarias, camaras, curvaK, radio, serie, perfil, pronostico, demografia, comunasGeo,
    coberturaPob, equidad, victimas, resumen,
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
    traer<PerfilTemporal>("/data/perfil_temporal.json"),
    traer<Pronostico>("/data/pronostico.json"),
    traer<Demografia>("/data/demografia.json"),
    traer<ComunasGeoJSON>("/data/comunas.geojson"),
    traer<CoberturaPoblacion>("/data/cobertura_poblacion.json"),
    traer<EquidadCobertura>("/data/equidad_cobertura.json"),
    traer<Victimas>("/data/victimas.json"),
    traer<Resumen>("/data/resumen.json"),
  ]);
  return { barrios, comunas, moduloA, moduloB, moduloC, comisarias, camaras,
           curvaK, radio, serie, perfil, pronostico, demografia, comunasGeo, coberturaPob, equidad, victimas, resumen };
}
