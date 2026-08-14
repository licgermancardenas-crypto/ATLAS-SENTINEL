/** Escala de color del mapa.
 *
 *  Cortes por cuantil y no lineales: el riesgo está muy sesgado a la derecha
 *  (unos pocos barrios del microcentro con valores enormes y una cola larga),
 *  así que una escala lineal deja 40 barrios del mismo color y no distingue
 *  nada. Con quintiles cada clase tiene ~10 barrios y el mapa informa.
 *
 *  Los colores salen de tokens CSS, no de hex literales, para que la coropleta
 *  cambie con el tema junto con el resto de la interfaz.
 */

export const N_CLASES = 5;

export const VAR_RIESGO = ["--risk-1", "--risk-2", "--risk-3", "--risk-4", "--risk-5"] as const;

export function cortesPorCuantil(valores: number[], n = N_CLASES): number[] {
  const orden = [...valores].filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (orden.length === 0) return [];
  const cortes: number[] = [];
  for (let i = 1; i < n; i++) {
    const pos = (i / n) * (orden.length - 1);
    const bajo = Math.floor(pos);
    const alto = Math.ceil(pos);
    cortes.push(orden[bajo] + (orden[alto] - orden[bajo]) * (pos - bajo));
  }
  return cortes;
}

export function claseDe(valor: number, cortes: number[]): number {
  for (let i = 0; i < cortes.length; i++) if (valor <= cortes[i]) return i;
  return cortes.length;
}

/** Lee el valor real de un token CSS. Hace falta porque Leaflet pinta los
 *  polígonos con un string de color en JS, no con clases, así que no puede
 *  heredar el token por cascada. */
export function leerToken(nombre: string, fallback = "#cccccc"): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(nombre);
  return v.trim() || fallback;
}

export function paletaRiesgo(): string[] {
  return VAR_RIESGO.map((v) => leerToken(v));
}

export const ETIQUETAS_CLASE = ["Muy bajo", "Bajo", "Medio", "Alto", "Muy alto"];
