export type Turno = "manana" | "tarde" | "noche" | "madrugada";

export const TURNOS: { key: Turno; label: string }[] = [
  { key: "manana", label: "Mañana" },
  { key: "tarde", label: "Tarde" },
  { key: "noche", label: "Noche" },
  { key: "madrugada", label: "Madrugada" },
];

export interface HexProperties {
  hex_id: string;
  barrio: string;
  comuna: number;
  riesgo_manana: number;
  riesgo_tarde: number;
  riesgo_noche: number;
  riesgo_madrugada: number;
}

export interface ModuloA {
  candidato_id: string;
  nombre: string;
  tipo: "comisaría existente" | "hexágono candidato";
  comuna: number;
  lat: number;
  lon: number;
}

export interface ModuloB {
  ranking: number;
  hex_id: string;
  lat: number;
  lon: number;
  ganancia_marginal: number;
}

export interface ModuloC {
  nombre: string;
  autopista: string;
  lat: number;
  lon: number;
  /** accesos de la fuente que caen en el mismo nodo del grafo y se agruparon
   *  como un solo corredor (el caso Illia: 3 entradas, un intercambiador) */
  n_accesos_agrupados: number;
  hexes_corredor: string[];
  /** total crudo de siniestros del corredor — se conserva para auditar, pero
   *  el ranking NO lo usa: los corredores varían 7,3x en tamaño */
  accidentalidad_corredor: number;
  /** la que entra al score: intensiva, comparable entre corredores */
  accidentalidad_por_hex: number;
  riesgo_delictivo_corredor: number;
  tramos_troncales: number;
  tramos_distribuidores: number;
  hexagonos_en_corredor: number;
  nodos_alcanzados: number;
  pct_accidentalidad: number;
  pct_riesgo: number;
  score_control: number;
  ranking: number;
}

export interface EvolucionMes {
  mes: string;
  mae: number;
  recall_20pct: number;
  delitos_reales: number;
}

export interface CalibracionDecil {
  decil: number;
  pred_medio: number;
  real_medio: number;
  n: number;
}

export interface Metricas {
  v1_vs_v2: {
    v1: { mae: number; recall_20: number; recall_30: number };
    v2: { mae: number; recall_20: number; recall_30: number };
    baseline_naive: { mae: number; recall_20: number; recall_30: number };
  };
  modulo_a_cobertura: {
    actual_75_comisarias: number;
    k20: number;
    k40: number;
    k75: number;
  };
  evolucion_mensual: EvolucionMes[];
  calibracion: CalibracionDecil[];
  shap_importancia: { feature: string; importancia_shap: number }[];
}
