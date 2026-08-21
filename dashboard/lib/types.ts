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

/* ---------------------------------------------------------- qué pinta el mapa
 *
 *  Hasta acá el mapa dibujaba siempre riesgo por barrio y lo único elegible
 *  era la capa de puntos encima. La demografía agrega superficies que no son
 *  riesgo y que además **viven en otra unidad espacial**: la edad solo existe
 *  por comuna. Por eso la superficie es un estado propio y no un modo del
 *  filtro de tipo — cambia la geometría que se dibuja, no solo el color.
 */

export type Superficie = "riesgo" | "densidad" | "mayores" | "chicos";

export const SUPERFICIES: {
  key: Superficie; label: string; corto: string; descripcion: string;
  /** Unidad espacial real del dato, que es la que se dibuja. Cada superficie
   *  usa la más fina que exista para ella: la densidad llega a barrio porque
   *  población y superficie están por barrio; la edad se queda en comuna. */
  unidad: "barrio" | "comuna";
  /** Campo demográfico a pintar. Vacío para el riesgo, que sale de otro lado. */
  campo?: "densidad" | "pct_65" | "pct_0_14";
  /** Cómo se escriben los cortes de la leyenda. */
  formato: "riesgo" | "pct" | "entero";
}[] = [
  { key: "riesgo", label: "Riesgo por barrio", corto: "Riesgo", unidad: "barrio",
    formato: "riesgo",
    descripcion: "Score del modelo por barrio y turno" },
  { key: "densidad", label: "Densidad de población", corto: "Densidad", unidad: "barrio",
    campo: "densidad", formato: "entero",
    descripcion: "Habitantes por km², Censo 2010 · por barrio" },
  { key: "mayores", label: "Edad · 65 y más", corto: "65 y más", unidad: "comuna",
    campo: "pct_65", formato: "pct",
    descripcion: "% de población de 65 años y más, Censo 2022 · solo hay dato por comuna" },
  { key: "chicos", label: "Edad · 0 a 14", corto: "0 a 14", unidad: "comuna",
    campo: "pct_0_14", formato: "pct",
    descripcion: "% de población de 0 a 14 años, Censo 2022 · solo hay dato por comuna" },
];

export const superficieInfo = (s: Superficie) => SUPERFICIES.find((x) => x.key === s)!;

/** Si lo que se está dibujando es demografía y no el modelo. */
export const esDemografica = (s: Superficie) => s !== "riesgo";

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

/* --------------------------------------------------------------- pronóstico
 *
 *  El pronóstico mensual es a nivel Ciudad y nada más: la serie que modela es
 *  una sola, de 120 meses. No se puede recortar por comuna ni por barrio sin
 *  inventar el dato, así que el componente ignora esos filtros y lo dice. Por
 *  tipo sí existe, con el modelo elegido, y por eso `por_tipo` viene aparte.
 */

export interface MesPronostico {
  /** 1-12. El año es el del objeto padre. */
  mes: number;
  yhat: number;
  lo: number;
  hi: number;
}

export interface ModeloPronostico {
  key: string;
  label: string;
  nota: string;
  /** Promedio mensual de los doce meses pronosticados. */
  mensual: number;
  total: number;
  /** Variación contra el promedio mensual del último año cerrado. */
  vs_base: number;
  banda: [number, number];
  mae_normal: number;
  mape_normal: number;
  sesgo_normal: number;
  cobertura_normal: number;
  /** Error del mismo modelo en 2025, el año del quiebre. */
  mae_quiebre: number;
  sesgo_quiebre: number;
  /** Doce posiciones, MAE a horizonte 1..12 meses. */
  mae_por_h: number[];
  meses: MesPronostico[];
}

export interface TipoPronostico {
  key: string;
  label: string;
  mensual: number;
  base_mensual: number;
  vs_base: number | null;
  banda: [number, number];
  meses: MesPronostico[];
}

export interface Pronostico {
  anio: number;
  elegido: string;
  base: { anio: number; total: number; mensual: number };
  backtest: {
    n_origenes: number; desde: string; hasta: string;
    horizonte: number; n_evaluaciones_normales: number;
  };
  modelos: ModeloPronostico[];
  por_tipo: TipoPronostico[];
  salvedad: string;
}

/* -------------------------------------------------------------- demografía
 *
 *  Dos censos conviven acá y no se pueden mezclar en una cuenta. Población,
 *  sexo y densidad son Censo 2010 —el mismo de los radios censales, y por lo
 *  tanto el mismo de NBI y hacinamiento—. La estructura etaria es Censo 2022,
 *  el único que la publica con desglose espacial, y solo llega hasta la
 *  comuna: por barrio no existe. Por eso `DemoBarrio` no tiene campos de edad
 *  en vez de tenerlos en null — que no exista es parte del tipo.
 */

export interface DemoBarrio {
  nombre: string;
  comuna: number | null;
  poblacion: number;
  varones: number;
  mujeres: number;
  area_km2: number | null;
  densidad: number | null;
}

export interface DemoComuna extends Omit<DemoBarrio, "nombre"> {
  comuna: number;
  /** Población del Censo 2022, la que corresponde a los porcentajes de edad. */
  poblacion_2022: number;
  pct_0_14: number;
  pct_15_64: number;
  pct_65: number;
  pct_80: number;
  hab_0_14: number;
  hab_15_64: number;
  hab_65: number;
  /** (65+ / 0-14) × 100. Arriba de 100 hay más viejos que chicos. */
  envejecimiento: number;
  /** ((0-14 + 65+) / 15-64) × 100. */
  dependencia: number;
}

export type ComunasGeoJSON = FeatureCollection<Polygon | MultiPolygon, DemoComuna>;

export interface Demografia {
  poblacion: {
    anio: number; total: number; varones: number; mujeres: number;
    area_km2: number; densidad: number; fuente: string;
  };
  edad: {
    anio: number; total: number;
    hab_0_14: number; hab_15_64: number; hab_65: number;
    pct_0_14: number; pct_15_64: number; pct_65: number; fuente: string;
  };
  barrios: DemoBarrio[];
  comunas: DemoComuna[];
  notas: {
    edad_solo_comuna: string;
    edad_derivada: string;
    dos_censos: string;
    denominador: string;
  };
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
  perfil: PerfilTemporal;
  pronostico: Pronostico;
  demografia: Demografia;
  comunasGeo: ComunasGeoJSON;
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
 *  Es un corte relativo y no absoluto a propósito: no existe un umbral
 *  "verdadero" de cuánta gente de afuera infla una tasa, pero sí se puede decir
 *  cuáles son los barrios donde más pesa.
 *
 *  0,75 y no 0,80 porque el índice solo ve transporte motorizado —subte, tren
 *  y bici— y por lo tanto subestima a los barrios que reciben gente a pie o en
 *  colectivo. Con 0,80 quedaban afuera San Telmo (0,79) y Recoleta (0,77), que
 *  son turismo y peatonal: dos casos donde la tasa está claramente inflada y
 *  el índice no lo ve del todo. Ante un instrumento que se sabe conservador,
 *  conviene errar marcando de más: el costo de un asterisco sobrante es que
 *  alguien mire un número con más cuidado del necesario. */
export const UMBRAL_PRESION = 0.75;

export const tasaInflada = (presion: number | null | undefined) =>
  presion != null && presion >= UMBRAL_PRESION;
