/** Formato es-AR en un solo lugar: punto de miles, coma decimal. Si cada
 *  componente formatea por su cuenta, el tablero termina mezclando 1,234 con
 *  1.234 en la misma pantalla. */

const nf = (min: number, max: number) =>
  new Intl.NumberFormat("es-AR", { minimumFractionDigits: min, maximumFractionDigits: max });

const entero = nf(0, 0);
const dec1 = nf(1, 1);
const dec2 = nf(2, 2);
const dec3 = nf(3, 3);

export const num = (v: number) => entero.format(v);
export const num1 = (v: number) => dec1.format(v);
export const num2 = (v: number) => dec2.format(v);
export const num3 = (v: number) => dec3.format(v);

/** Fracción 0-1 a porcentaje. */
export const pct = (v: number, decimales = 1) =>
  `${(decimales === 0 ? entero : dec1).format(v * 100)}%`;

/** Puntos porcentuales, con signo — para diferencias entre dos porcentajes. */
export const pp = (v: number) => `${v >= 0 ? "+" : "−"}${dec1.format(Math.abs(v) * 100)} pp`;

/** Variación relativa con signo, para los deltas de las tarjetas. */
export const delta = (v: number) => `${v >= 0 ? "+" : "−"}${dec1.format(Math.abs(v) * 100)}%`;

export const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                      "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];
