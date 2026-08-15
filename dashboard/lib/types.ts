import type { FeatureCollection, Polygon, MultiPolygon } from "geojson";

export type Turno = "manana" | "tarde" | "noche" | "madrugada";

export const TURNOS: { key: Turno; label: string; corto: string }[] = [
  { key: "manana", label: "Mañana", corto: "Mañ" },
  { key: "tarde", label: "Tarde", corto: "Tar" },
  { key: "noche", label: "Noche", corto: "Noc" },
  { key: "madrugada", label: "Madrugada", corto: "Mad" },
];

/* ------------------------------------------------------------ tipo de delito
 *
 *  El filtro por tipo tiene una asimetría que hay que respetar en la interfaz:
 *  los seis tipos tienen delitos registrados, pero solo cuatro tienen una
 *  superficie de riesgo propia. Vialidad y Homicidios quedaron fuera de esa
 *  superficie por decisión medida (son siniestros viales; y 78 hechos en el año
 *  de test), no por olvido — ver README, "Riesgo por tipo en los módulos".
 *
 *  Para esos dos, el tablero filtra los delitos pero sigue dibujando el riesgo
 *  agregado, y lo dice en pantalla. Por eso `superficie` es explícito acá y no
 *  algo que cada componente deduzca por su cuenta.
 */

export type TipoDelito =
  | "todos" | "robo" | "hurto" | "lesiones" | "amenazas" | "vialidad" | "homicidios";

/** `uno` es el singular con artículo ("un robo", "una lesión"). Va como campo y
 *  no derivado del label porque el español no permite deducirlo: hay que saber
 *  el género y que el plural de "vialidad" en estos datos son siniestros. */
export const TIPOS: {
  key: TipoDelito; label: string; uno: string; superficie: boolean; nota?: string;
}[] = [
  { key: "todos", label: "Todos los tipos", uno: "un delito", superficie: true },
  { key: "robo", label: "Robo", uno: "un robo", superficie: true },
  { key: "hurto", label: "Hurto", uno: "un hurto", superficie: true },
  { key: "lesiones", label: "Lesiones", uno: "una lesión", superficie: true },
  { key: "amenazas", label: "Amenazas", uno: "una amenaza", superficie: true },
  { key: "vialidad", label: "Vialidad", uno: "un siniestro vial", superficie: false,
    nota: "Son siniestros viales, no delitos de seguridad: quedaron excluidos de la superficie de riesgo." },
  { key: "homicidios", label: "Homicidios", uno: "un homicidio", superficie: false,
    nota: "78 hechos en el año de test y PEI 54%: muy pocos casos para una superficie de riesgo propia." },
];

export const tipoInfo = (t: TipoDelito) => TIPOS.find((x) => x.key === t)!;

/** Capa operativa que se superpone al mapa. Solo una a la vez: son propuestas
 *  de módulos distintos y mezclarlas en pantalla no significa nada. */
export type Capa = "ninguna" | "patrullas" | "camaras" | "controles";

export const CAPAS: { key: Capa; label: string; descripcion: string }[] = [
  { key: "ninguna", label: "Solo riesgo", descripcion: "El mapa de riesgo sin recomendaciones encima" },
  { key: "patrullas", label: "Módulo A · Patrullas", descripcion: "Ubicaciones propuestas contra las comisarías actuales" },
  { key: "camaras", label: "Módulo B · Cámaras", descripcion: "Esquinas propuestas contra las cámaras existentes" },
  { key: "controles", label: "Módulo C · Controles", descripcion: "Accesos de autopista rankeados" },
];

/** Las claves por tipo son `riesgo_{tipo}_{turno}` y `delitos_{tipo}`. Se
 *  declaran como índice y no una por una porque son 16 + 6 campos: enumerarlas
 *  no agrega seguridad de tipos real, solo ruido. Los accesos pasan siempre por
 *  `claveRiesgo`/`claveDelitos`, que son las que garantizan el nombre. */
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
  [clave: string]: string | number | null;
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
  [clave: string]: number;
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

/** Cuándo ocurren los delitos. Cada corte es {tipo -> conteos}, con "todos"
 *  incluido, para que los perfiles sigan el filtro de tipo del tablero: el
 *  perfil horario de vialidad y el de robo no se parecen en nada. */
export interface PerfilTemporal {
  anio: number;
  /** Días efectivamente cubiertos por los datos. No asumir 365. */
  dias: number;
  totales: Record<string, number>;
  /** 24 posiciones, hora 0 a 23. */
  franja: Record<string, number[]>;
  /** 7 posiciones, en el orden de `dias_orden` (arranca lunes). */
  dia_semana: Record<string, number[]>;
  /** 4 posiciones: mañana, tarde, noche, madrugada. */
  turno: Record<string, number[]>;
  dias_orden: string[];
}

export const TURNOS_PERFIL = ["Mañana", "Tarde", "Noche", "Madrugada"];

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
  perfil: PerfilTemporal;
  resumen: Resumen;
}

/** Nombre del campo de riesgo a leer. Un solo lugar decide el fallback: si el
 *  tipo elegido no tiene superficie propia, se devuelve la clave del agregado.
 *  Si esto viviera repartido por los componentes, alcanzaría con que uno se
 *  olvidara para que el mapa dibujara ceros y pareciera "sin riesgo". */
export const claveRiesgo = (t: Turno, tipo: TipoDelito = "todos") =>
  tipo === "todos" || !tipoInfo(tipo).superficie ? `riesgo_${t}` : `riesgo_${tipo}_${t}`;

/** Nombre del campo de delitos registrados. Acá no hay fallback: los seis tipos
 *  tienen conteo propio, incluidos los dos que no tienen superficie. */
export const claveDelitos = (tipo: TipoDelito = "todos") =>
  tipo === "todos" ? "delitos_2025" : `delitos_${tipo}`;

/** Si el riesgo que se está dibujando corresponde al tipo elegido o al
 *  agregado. Lo consultan el encabezado del mapa y el KPI para decirlo. */
export const riesgoEsDelTipo = (tipo: TipoDelito) =>
  tipo !== "todos" && tipoInfo(tipo).superficie;

/** Percentil de afluencia no residente arriba del cual se marca la tasa.
 *
 *  0,8 deja marcado el quinto superior. Es un corte relativo y no absoluto a
 *  propósito: no existe un umbral "verdadero" de cuánta gente de afuera infla
 *  una tasa, pero sí se puede decir cuáles son los barrios donde más pesa. */
export const UMBRAL_PRESION = 0.8;

export const tasaInflada = (presion: number | null | undefined) =>
  presion != null && presion >= UMBRAL_PRESION;
