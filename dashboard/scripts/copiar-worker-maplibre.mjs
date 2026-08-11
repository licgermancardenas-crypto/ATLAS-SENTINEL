/**
 * Copia el worker de MapLibre y su chunk compartido a public/maplibre/.
 *
 * POR QUÉ EXISTE ESTE SCRIPT
 * MapLibre v6 se distribuye en tres piezas: el módulo principal, un chunk
 * compartido y un web worker. El worker es ESM y arranca con
 *
 *     import { ... } from "./maplibre-gl-shared.mjs";
 *
 * Turbopack emite esos archivos en /_next/static/immutable/media/ con hash en
 * el nombre (maplibre-gl-shared.24yiwt8m1vm6z.mjs), y reescribe el import del
 * módulo principal para que apunte al hasheado. Pero NO reescribe el import
 * que está dentro del archivo del worker: queda pidiendo el nombre sin hash,
 * que devuelve 404.
 *
 * El worker entonces falla al cargar. Como `new Worker(url, {type:"module"})`
 * no lanza excepción cuando el módulo no resuelve —el fallo llega como evento
 * en el worker, que MapLibre no escucha— el mapa se queda esperando el estilo
 * sin emitir un solo error: canvas en negro, cero tiles pedidas.
 *
 * La solución es servir el par nosotros. En public/maplibre/ los dos archivos
 * conviven SIN hash, así que el import relativo del worker resuelve, y se le
 * indica la ruta a MapLibre con setWorkerUrl() (ver RiskMap.tsx).
 *
 * Corre como `prebuild`, así que se re-copia en cada build y no queda una
 * versión vieja pegada si se actualiza maplibre-gl.
 */

import { copyFileSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = join(dirname(fileURLToPath(import.meta.url)), "..");
const ORIGEN = join(RAIZ, "node_modules", "maplibre-gl", "dist");
const DESTINO = join(RAIZ, "public", "maplibre");

const ARCHIVOS = ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"];

const version = JSON.parse(
  readFileSync(join(RAIZ, "node_modules", "maplibre-gl", "package.json"), "utf8")
).version;

mkdirSync(DESTINO, { recursive: true });
for (const archivo of ARCHIVOS) {
  copyFileSync(join(ORIGEN, archivo), join(DESTINO, archivo));
}

console.log(`[maplibre] worker ${version} copiado a public/maplibre/ (${ARCHIVOS.join(", ")})`);
