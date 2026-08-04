// Rampa secuencial azul validada (dataviz skill) — 100 = riesgo bajo, 700 = alto.
export const RISK_RAMP = [
  "#cde2fb", // 100
  "#9ec5f4", // 200
  "#6da7ec", // 300
  "#3987e5", // 400
  "#256abf", // 500
  "#184f95", // 600
  "#0d366b", // 700
];

/** Breakpoints por cuantil sobre los valores actuales — así la rampa
 * siempre usa los 7 pasos, sea cual sea la distribución del turno elegido
 * (el riesgo está muy sesgado: la mayoría de los hex son bajos, una cola
 * larga es alta — una escala lineal dejaría casi todo en el mismo color). */
export function quantileBreaks(valores: number[], nBins: number): number[] {
  const ordenados = [...valores].sort((a, b) => a - b);
  const breaks: number[] = [];
  for (let i = 1; i < nBins; i++) {
    const idx = Math.floor((i / nBins) * ordenados.length);
    breaks.push(ordenados[Math.min(idx, ordenados.length - 1)]);
  }
  return breaks;
}

// El tipo de expresión de MapLibre depende genéricamente de la propiedad de
// paint que reciba (fill-color, line-width, etc.) — se tipa laxo acá adrede
// en vez de pelear con esos genéricos, y se castea en el punto de uso.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function colorScaleExpression(propiedad: string, breaks: number[]): any {
  const stops: unknown[] = ["step", ["get", propiedad], RISK_RAMP[0]];
  breaks.forEach((b, i) => {
    stops.push(b, RISK_RAMP[i + 1]);
  });
  return stops;
}
