import type { FeatureCollection, Polygon, MultiPolygon } from "geojson";

export type Turno = "manana" | "tarde" | "noche" | "madrugada";

export const TURNOS: { key: Turno; label: string; corto: string }[] = [
  { key: "manana", label: "Mañana", corto: "Mañ" },
  { key: "tarde", label: "Tarde", corto: "Tar" },
  { key: "noche", label: "Noche", corto: "Noc" },
  { key: "madrugada", label: "Madrugada", corto: "Mad" },
];

/** Capa operativa que se superpone al mapa. Solo una a la vez: son propuestas
 *  de módulos distintos y mezclarlas en pantalla no significa nada. */
export type Capa = "ninguna" | "patrullas" | "camaras" | "controles";

export const CAPAS: { key: Capa; label: string; descripcion: string }[] = [
  { key: "ninguna", label: "Solo riesgo", descripcion: "El mapa de riesgo sin recomendaciones encima" },
  { key: "patrullas", label: "Módulo A · Patrullas", descripcion: "Ubicaciones propuestas contra las comisarías actuales" },
  { key: "camaras", label: "Módulo B · Cámaras", descripcion: "Esquinas propuestas contra las cámaras existentes" },
  { key: "controles", label: "Módulo C · Controles", descripcion: "Accesos de autopista rankeados" },
];

export interface BarrioProps {
  nombre: string;
  comuna: number | null;
  n_hex: number;
  delitos_2025: number;
  riesgo_manana: number;
  riesgo_tarde: number;
  riesgo_noche: number;
  riesgo_madrugada: number;
  riesgo_total_manana: number;
  riesgo_total_tarde: number;
  riesgo_total_noche: number;
  riesgo_total_madrugada: number;
}

export type BarriosGeoJSON = FeatureCollection<Polygon | MultiPolygon, BarrioProps>;

export interface ComunaResumen {
  comuna: number;
  n_hex: number;
  n_barrios: number;
  delitos_2025: number;
  riesgo_manana: number;
  riesgo_tarde: number;
  riesgo_noche: number;
  riesgo_madrugada: number;
}

export interface PuntoModuloA {
  candidato_id: string;
  nombre: string;
  tipo: "comisaría existente" | "hexágono candidato";
  comuna: number;
  lat: number;
  lon: number;
}

export interface PuntoModuloB {
  ranking: number;
  nodo?: number;
  hex_id: string;
  lat: number;
  lon: number;
  ganancia_marginal: number;
  tramos_cubiertos: number;
  peso_total?: number;
}

export interface PuntoModuloC {
  nombre: string;
  autopista: string;
  lat: number;
  lon: number;
  ranking: number;
  n_accesos_agrupados: number;
  accidentalidad_por_hex: number;
  riesgo_delictivo_corredor: number;
  score_control: number;
  hexagonos_en_corredor: number;
}

export interface PuntoCurvaK {
  k: number;
  estado: string;
  cobertura: number | null;
  reusa_comisaria?: number;
  puestos_nuevos?: number;
}

export interface CurvaK {
  turno: string;
  radio_m: number;
  n_demanda: number;
  n_candidatos: number;
  n_comisarias: number;
  n_comunas: number;
  cobertura_actual: number;
  curva: PuntoCurvaK[];
}

export interface FilaRadio {
  radio_m: number;
  cobertura_actual: number;
  cobertura_k_titular?: number;
  ganancia_pp?: number;
  ganancia_relativa?: number;
  cruce_k: number | null;
  solape_plan_vs_800?: number | null;
}

export interface SensibilidadRadio {
  turno: string;
  k_titular: number;
  radios: FilaRadio[];
}

export interface FilaSerie {
  anio: number;
  mes: number;
  tipo: string;
  n: number;
}

export interface Resumen {
  periodo: { desde: number; hasta: number };
  delitos_ultimo_anio: number;
  delitos_anio_previo: number;
  n_hexagonos: number;
  n_barrios: number;
  n_comunas: number;
  modelo: {
    mae: number; mae_naive: number;
    recall_20: number; recall_20_naive: number;
    pai_10: number; pei_10: number;
    concentracion_30pct_area: number;
  };
  modulo_a: { cobertura_actual: number; n_comisarias: number; radio_m: number; turno: string };
  modulo_b: { n_camaras_existentes: number; cobertura_30_camaras: number; km_cubiertos_30: number; km_red: number };
  modulo_c: { n_corredores: number; primero: string; siniestros_km_primero: number };
  salvedades: string[];
}

export interface DatosDashboard {
  barrios: BarriosGeoJSON;
  comunas: ComunaResumen[];
  moduloA: PuntoModuloA[];
  moduloB: PuntoModuloB[];
  moduloC: PuntoModuloC[];
  comisarias: FeatureCollection;
  camaras: FeatureCollection;
  curvaK: CurvaK;
  radio: SensibilidadRadio;
  serie: FilaSerie[];
  resumen: Resumen;
}

export const claveRiesgo = (t: Turno) =>
  `riesgo_${t}` as keyof Pick<
    BarrioProps,
    "riesgo_manana" | "riesgo_tarde" | "riesgo_noche" | "riesgo_madrugada"
  >;
