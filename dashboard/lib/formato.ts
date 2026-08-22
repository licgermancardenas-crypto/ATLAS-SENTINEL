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

/** Diferencia entre dos porcentajes, con signo.
 *
 *  Dice "puntos" y no "pp": la abreviatura es estándar en análisis y opaca para
 *  todos los demás, y el ahorro de dos caracteres no compra nada. La palabra
 *  completa además evita la confusión con "por ciento", que es el error que la
 *  unidad existe para prevenir. */
export const pp = (v: number) => `${v >= 0 ? "+" : "−"}${dec1.format(Math.abs(v) * 100)} puntos`;

/** Variación relativa con signo, para los deltas de las tarjetas. */
export const delta = (v: number) => `${v >= 0 ? "+" : "−"}${dec1.format(Math.abs(v) * 100)}%`;

export const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                      "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** "un delito cada 4 minutos" — la unidad se elige sola.
 *
 *  Hace falta porque el rango es enorme: son 130.421 delitos al año (uno cada
 *  4 minutos) pero 78 homicidios (uno cada 4,7 días). Fijar la unidad en
 *  minutos dejaría "cada 6.735 minutos", que no se puede dimensionar. La regla
 *  es quedarse en la unidad más grande que todavía dé un número mayor que 1.
 */
export function cadaCuanto(n: number, dias: number): { valor: string; unidad: string } {
  if (n <= 0) return { valor: "—", unidad: "" };
  const seg = (dias * 86400) / n;
  const escalas: [number, string, string][] = [
    [86400, "día", "días"],
    [3600, "hora", "horas"],
    [60, "minuto", "minutos"],
    [1, "segundo", "segundos"],
  ];
  for (const [factor, sing, plu] of escalas) {
    const v = seg / factor;
    if (v >= 1) {
      // un decimal solo si el entero pierde información útil (1,5 días sí,
      // 4,0 minutos no)
      const redondeado = v >= 10 ? Math.round(v) : Math.round(v * 10) / 10;
      const texto = Number.isInteger(redondeado) ? entero.format(redondeado) : dec1.format(redondeado);
      return { valor: texto, unidad: redondeado === 1 ? sing : plu };
    }
  }
  return { valor: dec1.format(seg), unidad: "segundos" };
}

/** Tasa cada 100.000 habitantes. `null` si no hay población — no se inventa 0,
 *  que se leería como "acá no pasa nada". */
export const tasa100k = (delitos: number, poblacion: number) =>
  poblacion > 0 ? (delitos / poblacion) * 100_000 : null;
