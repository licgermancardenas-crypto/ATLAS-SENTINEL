"use client";

/* Vista 3D de la Ciudad: el tejido construido real, extruido, con las capas
   operativas encima.
 *
 * POR QUÉ MAPLIBRE Y NO LEAFLET
 * El resto del tablero usa Leaflet, que no hace 3D. Esta vista necesita WebGL sí
 * o sí. Se verificó antes de escribir nada que la máquina lo aguanta: WebGL2 por
 * ANGLE/D3D11, y 4.900 extrusiones girando a 60 fps sin perder el contexto.
 *
 * POR QUÉ TESELAS Y NO GEOJSON
 * El tejido son 1.019.395 volúmenes tras limpiar. Como GeoJSON son ~100 MB y no
 * hay navegador que los cargue; como PMTiles el navegador pide por rango HTTP
 * solo las teselas que está mirando. Se generan con
 * `pipeline/ingest_tejido_urbano.py`.
 *
 * QUÉ SE PINTA Y QUÉ NO
 * Los edificios van en gris que aclara con la altura y NO se colorean por
 * riesgo. Es a propósito: el riesgo depende del turno y del tipo de delito, y
 * hornear eso en las teselas obligaría a regenerarlas por cada combinación. El
 * riesgo va como capa de piso, debajo de los edificios, que se cambia al vuelo.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import type { FeatureCollection, Feature, Polygon } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";

import type { PuntoModuloA, PuntoModuloB, Turno } from "@/lib/types";
import { cortesPorCuantil, ETIQUETAS_CLASE } from "@/lib/escala";

/* Arranca sobre el microcentro y no sobre el centroide de la Ciudad, y de cerca
   y no de lejos. Es por una razón medida, no estética: a z12 la Ciudad entera
   entra en pantalla pero un edificio de 20 m de frente ocupa medio píxel, así
   que el tejido es invisible aunque esté dibujándose. Recién desde z14 la
   volumetría se lee. Alejar sigue estando disponible con la rueda; lo que no
   se puede es arrancar en un encuadre donde no se ve nada. */
const CENTRO: [number, number] = [-58.3816, -34.6037];
const ZOOM_INICIAL = 14.6;
const LIMITES: [number, number, number, number] = [-58.55, -34.71, -58.33, -34.52];

/* Radio real del Módulo A, el mismo que reporta resumen.json. No se inventa:
   si el número cambia en el modelo, hay que cambiarlo acá también. */
const RADIO_PATRULLA_M = 800;

/* Paleta de riesgo en hex y no en tokens CSS: MapLibre resuelve los colores
   dentro del canvas WebGL, donde la cascada no llega. Son los mismos cinco
   pasos que usa la coropleta 2D. */
const PALETA_RIESGO = ["#1d3a5c", "#2b5f8a", "#3d8bb5", "#e8a33d", "#c94f38"];

const CAPAS = [
  { key: "riesgo", label: "Riesgo" },
  { key: "camaras", label: "Cámaras" },
  { key: "patrullas", label: "Patrullas" },
  { key: "ninguna", label: "Solo ciudad" },
] as const;
type CapaTres = (typeof CAPAS)[number]["key"];

const TURNOS: { key: Turno; label: string }[] = [
  { key: "madrugada", label: "Madrugada" },
  { key: "manana", label: "Mañana" },
  { key: "tarde", label: "Tarde" },
  { key: "noche", label: "Noche" },
];

interface HexProps {
  hex_id: string;
  barrio: string;
  comuna: number;
  [k: string]: string | number;
}

interface Datos {
  hex: FeatureCollection<Polygon, HexProps>;
  camaras: FeatureCollection;
  comisarias: FeatureCollection;
  moduloA: PuntoModuloA[];
  moduloB: PuntoModuloB[];
}

/** Círculo real en metros. MapLibre solo sabe de radios en píxeles, así que un
 *  radio de cobertura de 800 m hay que dibujarlo como polígono o se agranda y
 *  achica con el zoom, que es exactamente lo que no queremos. */
function circulo(lon: number, lat: number, radioM: number, pasos = 48): Feature<Polygon> {
  const dLat = radioM / 111_320;
  const dLon = radioM / (111_320 * Math.cos((lat * Math.PI) / 180));
  const anillo: [number, number][] = [];
  for (let i = 0; i <= pasos; i++) {
    const a = (i / pasos) * 2 * Math.PI;
    anillo.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [anillo] } };
}

const vacio: FeatureCollection = { type: "FeatureCollection", features: [] };

/** Textura de fachada, dibujada en un canvas en vez de traída de un archivo.
 *
 *  Es una grilla de ventanas con algunas encendidas. Se genera por código para
 *  no versionar un PNG ni depender de nada externo, y con semilla fija para que
 *  el patrón sea igual en cada carga (si cambiara, el mismo edificio tendría
 *  otras luces prendidas cada vez que se recarga).
 *
 *  Hay que decir qué es: **decoración, no dato**. El Tejido Urbano da huella y
 *  altura, no fachadas. Una torre de Puerto Madero y una casa de Villa Devoto
 *  reciben exactamente la misma ventana. Sirve para que el volumen se lea como
 *  edificio; no dice nada del edificio.
 */
function texturaFachada(): ImageData {
  const L = 64, canvas = document.createElement("canvas");
  canvas.width = canvas.height = L;
  const c = canvas.getContext("2d")!;
  c.fillStyle = "#2a2f38";
  c.fillRect(0, 0, L, L);

  let semilla = 7;
  const azar = () => (semilla = (semilla * 1103515245 + 12345) % 2147483648) / 2147483648;

  const paso = 8, margen = 2;
  for (let y = 0; y < L; y += paso) {
    for (let x = 0; x < L; x += paso) {
      const r = azar();
      // una de cada cinco encendida; el resto, vidrio oscuro
      c.fillStyle = r > 0.8 ? "#ffdca1" : r > 0.55 ? "#3d444f" : "#1c2027";
      c.fillRect(x + margen, y + margen, paso - margen * 2, paso - margen * 2);
    }
  }
  return c.getImageData(0, 0, L, L);
}

let protocoloRegistrado = false;

/* La misma pintura para las dos capas de edificios (hitos y detalle): gris que
   aclara con la altura. Es lo que da la lectura de silueta de las referencias,
   sin pintarle dato encima. Va en una constante para que no se desincronicen —
   si las dos capas no se ven idénticas, al cruzar z14 la ciudad "parpadea". */
const PINTURA_EDIFICIO: maplibregl.FillExtrusionLayerSpecification["paint"] = {
  "fill-extrusion-height": ["get", "altura"],
  "fill-extrusion-base": 0,
  "fill-extrusion-opacity": 1,
  /* El degradado vertical de MapLibre oscurece la base de cada prisma. Es lo
     que separa una caja de un edificio: sin él, con 300.000 volúmenes pegados
     no se distingue dónde termina uno y empieza el otro. */
  "fill-extrusion-vertical-gradient": true,
  "fill-extrusion-color": [
    "interpolate", ["linear"], ["get", "altura"],
    0, "#1b1f26", 10, "#282d36", 25, "#39404c", 60, "#4e5766",
    120, "#6d7889", 200, "#8d99ab",
  ],
};

async function traer<T>(ruta: string): Promise<T> {
  const r = await fetch(ruta, { cache: "no-cache" });
  if (!r.ok) throw new Error(`No se pudo cargar ${ruta} (HTTP ${r.status})`);
  return r.json() as Promise<T>;
}

export default function Ciudad3D() {
  const contenedor = useRef<HTMLDivElement>(null);
  const mapa = useRef<maplibregl.Map | null>(null);
  // en ref y no en estado: el manejador de errores se registra una sola vez y
  // capturaría para siempre el valor inicial de un estado
  const cargado = useRef(false);
  const [listo, setListo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [datos, setDatos] = useState<Datos | null>(null);
  const [capa, setCapa] = useState<CapaTres>("riesgo");
  const [turno, setTurno] = useState<Turno>("tarde");
  const [sel, setSel] = useState<{ altura: number; lngLat: maplibregl.LngLat } | null>(null);
  const [oculto, setOculto] = useState(false);
  const [base, setBase] = useState<"oscura" | "satelital">("oscura");
  const [fachadas, setFachadas] = useState(false);

  /* MapLibre difiere el parseo del estilo con `requestAnimationFrame`, y el
     navegador no corre rAF en pestañas de segundo plano. O sea que si alguien
     abre esta vista en una pestaña de fondo, el mapa no llega ni a leer el
     estilo: se queda en cero fuentes y cero capas hasta que la pestaña pasa al
     frente. Se recupera solo —el rAF pendiente se dispara al volver— pero sin
     esto el usuario ve un "cargando" eterno y sin motivo. */
  useEffect(() => {
    const alCambiar = () => setOculto(document.hidden);
    alCambiar();
    document.addEventListener("visibilitychange", alCambiar);
    return () => document.removeEventListener("visibilitychange", alCambiar);
  }, []);

  /* --- datos --- */
  useEffect(() => {
    Promise.all([
      traer<FeatureCollection<Polygon, HexProps>>("/data/hex_riesgo.geojson"),
      traer<FeatureCollection>("/data/camaras.geojson"),
      traer<FeatureCollection>("/data/comisarias.geojson"),
      traer<PuntoModuloA[]>("/data/modulo_a_k75.json"),
      traer<PuntoModuloB[]>("/data/modulo_b_red.json"),
    ])
      .then(([hex, camaras, comisarias, moduloA, moduloB]) =>
        setDatos({ hex, camaras, comisarias, moduloA, moduloB }))
      .catch((e: Error) => setError(e.message));
  }, []);

  /* --- mapa --- */
  useEffect(() => {
    if (!contenedor.current || mapa.current) return;

    // el protocolo pmtiles es global al proceso, no del mapa: se registra una
    // sola vez. En desarrollo React monta los efectos dos veces, así que sin el
    // flag se registraría de nuevo en cada montaje.
    if (!protocoloRegistrado) {
      maplibregl.addProtocol("pmtiles", new Protocol().tile);
      protocoloRegistrado = true;
    }

    const m = new maplibregl.Map({
      container: contenedor.current,
      style: {
        version: 8,
        sources: {
          // dos juegos de teselas y no uno: ver el porqué en
          // pipeline/ingest_tejido_urbano.py — teselar un millón de volúmenes a
          // z12 es inviable, así que a escala de ciudad solo van los hitos
          tejido: { type: "vector", url: "pmtiles:///tejido/caba.pmtiles" },
          hitos: { type: "vector", url: "pmtiles:///tejido/caba_hitos.pmtiles" },
          // capa base: sin el río y la traza de calles el tejido flota en negro
          agua: { type: "geojson", data: "/tejido/agua.geojson" },
          verde: { type: "geojson", data: "/tejido/verde.geojson" },
          puentes: { type: "geojson", data: "/tejido/puentes.geojson" },
          calles: { type: "vector", url: "pmtiles:///tejido/calles.pmtiles" },
          // el Tejido Urbano es edificación por parcela, así que lo que está
          // parado en una plaza no existe ahí: el Obelisco entra por acá
          monumentos: { type: "geojson", data: "/tejido/monumentos.geojson" },
          // 350.660 árboles con altura medida y 102.700 luminarias
          arbolado: { type: "vector", url: "pmtiles:///tejido/arbolado.pmtiles" },
          alumbrado: { type: "vector", url: "pmtiles:///tejido/alumbrado.pmtiles" },
          /* Única capa que sale a internet. Va apagada por defecto y con
             interruptor: sin ella el tablero funciona entero sin conexión. */
          satelital: {
            type: "raster", tileSize: 256, maxzoom: 19,
            tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/"
                    + "World_Imagery/MapServer/tile/{z}/{y}/{x}"],
            attribution: "Imagen: Esri, Maxar, Earthstar Geographics",
          },
          riesgo: { type: "geojson", data: vacio },
          coberturas: { type: "geojson", data: vacio },
          puntos: { type: "geojson", data: vacio },
          destacado: { type: "geojson", data: vacio },
        },
        layers: [
          { id: "fondo", type: "background", paint: { "background-color": "#0a0c10" } },
          {
            id: "satelital-raster", type: "raster", source: "satelital",
            layout: { visibility: "none" },
            // se oscurece un poco: a plena luz la foto compite con los
            // edificios y el 3D deja de leerse
            paint: { "raster-opacity": 0.85, "raster-brightness-max": 0.9 },
          },
          {
            id: "agua-fill", type: "fill", source: "agua",
            paint: { "fill-color": "#0c1a2a", "fill-outline-color": "#16304a" },
          },
          {
            id: "verde-fill", type: "fill", source: "verde",
            paint: { "fill-color": "#122119", "fill-opacity": 0.9 },
          },
          {
            id: "riesgo-piso", type: "fill", source: "riesgo",
            paint: { "fill-color": ["get", "_color"], "fill-opacity": 0.45 },
          },
          /* Las calles con ancho que crece con el zoom, y las autopistas en
             ámbar. Es la jerarquía que ya trae el dato de la Ciudad
             (`tipo_via` × `jerarquia`), no una invención: sin ella todas las
             vías se dibujan igual y la traza no se lee. */
          {
            id: "calles-menores", type: "line", source: "calles",
            "source-layer": "calles", minzoom: 13,
            filter: ["match", ["get", "clase"], ["calle", "peatonal"], true, false],
            paint: {
              "line-color": "#20242b",
              "line-width": ["interpolate", ["exponential", 1.6], ["zoom"],
                             13, 0.4, 16, 3],
            },
          },
          {
            id: "calles-secundarias", type: "line", source: "calles",
            "source-layer": "calles", minzoom: 12,
            filter: ["==", ["get", "clase"], "secundaria"],
            paint: {
              "line-color": "#2a2f38",
              "line-width": ["interpolate", ["exponential", 1.6], ["zoom"],
                             12, 0.5, 16, 4.5],
            },
          },
          {
            id: "avenidas", type: "line", source: "calles",
            "source-layer": "calles",
            filter: ["==", ["get", "clase"], "avenida"],
            paint: {
              "line-color": "#3b424e",
              "line-width": ["interpolate", ["exponential", 1.6], ["zoom"],
                             11, 0.6, 16, 7],
            },
          },
          {
            id: "autopistas", type: "line", source: "calles",
            "source-layer": "calles",
            filter: ["==", ["get", "clase"], "autopista"],
            paint: {
              "line-color": "#c8963c",
              "line-opacity": 0.75,
              "line-width": ["interpolate", ["exponential", 1.6], ["zoom"],
                             11, 0.8, 16, 8],
            },
          },
          {
            id: "cobertura", type: "fill", source: "coberturas",
            paint: { "fill-color": "#4f8ef7", "fill-opacity": 0.12,
                     "fill-outline-color": "#4f8ef7" },
          },
          {
            // hasta z14: solo los edificios altos, que son los únicos que a
            // escala de ciudad miden más de un píxel
            id: "edificios-hitos", type: "fill-extrusion", source: "hitos",
            "source-layer": "tejido", maxzoom: 14,
            paint: PINTURA_EDIFICIO,
          },
          {
            id: "edificios", type: "fill-extrusion", source: "tejido",
            "source-layer": "tejido", minzoom: 14,
            paint: PINTURA_EDIFICIO,
          },
          {
            /* Copas de árbol. La base va al 45% de la altura por expresión y no
               como atributo: calcularlo acá ahorra mandar un segundo número por
               cada uno de los 350.660 ejemplares. */
            id: "arbolado-3d", type: "fill-extrusion", source: "arbolado",
            "source-layer": "arbolado", minzoom: 15,
            paint: {
              "fill-extrusion-height": ["get", "alt"],
              "fill-extrusion-base": ["*", ["get", "alt"], 0.45],
              "fill-extrusion-opacity": 0.95,
              "fill-extrusion-vertical-gradient": true,
              // más claro arriba: los árboles altos reciben más luz
              "fill-extrusion-color": [
                "interpolate", ["linear"], ["get", "alt"],
                2, "#1e3324", 8, "#27452e", 16, "#325a39", 30, "#3f7047",
              ],
            },
          },
          {
            // luminarias: el punto chico es el foco y el halo el resplandor
            id: "alumbrado-halo", type: "circle", source: "alumbrado",
            "source-layer": "alumbrado", minzoom: 15,
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 3, 16, 7],
              "circle-color": "#ffcf7a",
              "circle-opacity": 0.10,
              "circle-blur": 1,
            },
          },
          {
            id: "alumbrado-foco", type: "circle", source: "alumbrado",
            "source-layer": "alumbrado", minzoom: 15,
            paint: {
              "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 0.7, 16, 1.6],
              "circle-color": "#ffe6b0",
              "circle-opacity": 0.75,
            },
          },
          {
            // en piedra clara y no en el gris del tejido: un monumento no es un
            // edificio más, y si se pinta igual se pierde entre las medianeras
            id: "monumentos-3d", type: "fill-extrusion", source: "monumentos",
            paint: {
              "fill-extrusion-height": ["get", "altura"],
              "fill-extrusion-base": 0,
              "fill-extrusion-opacity": 1,
              "fill-extrusion-vertical-gradient": true,
              "fill-extrusion-color": "#b9b2a4",
            },
          },
          /* Los puentes van DESPUÉS de los edificios porque están elevados:
             dibujados debajo, el tejido de la ribera los tapa y la General Paz
             o la 25 de Mayo desaparecen justo donde cruzan. */
          {
            id: "puentes-linea", type: "line", source: "puentes",
            paint: {
              "line-color": ["match", ["get", "clase"],
                             "autopista", "#d9a441", "#6f7787"],
              "line-opacity": 0.85,
              "line-width": ["interpolate", ["exponential", 1.6], ["zoom"],
                             11, 0.8, 16, 6],
            },
          },
          {
            id: "destacado-3d", type: "fill-extrusion", source: "destacado",
            paint: {
              "fill-extrusion-height": ["get", "altura"],
              "fill-extrusion-base": 0,
              "fill-extrusion-color": "#4f8ef7",
              "fill-extrusion-opacity": 0.92,
            },
          },
          {
            id: "puntos-halo", type: "circle", source: "puntos",
            paint: {
              "circle-radius": ["case", ["==", ["get", "_clase"], "propuesto"], 9, 5],
              "circle-color": ["get", "_color"],
              "circle-opacity": 0.22,
            },
          },
          {
            id: "puntos", type: "circle", source: "puntos",
            paint: {
              "circle-radius": ["case", ["==", ["get", "_clase"], "propuesto"], 4.5, 2.5],
              "circle-color": ["get", "_color"],
              "circle-stroke-width": 1,
              "circle-stroke-color": "#0b0d10",
            },
          },
        ],
        /* Niebla y horizonte: es lo que da sensación de distancia. Sin esto la
           ciudad se corta en seco contra el fondo y el tejido lejano se ve tan
           nítido como el de adelante, que es justo lo que delata un render. */
        sky: {
          "sky-color": "#0e1420",
          "sky-horizon-blend": 0.6,
          "horizon-color": "#1b2532",
          "horizon-fog-blend": 0.7,
          "fog-color": "#0a0f16",
          "fog-ground-blend": 0.75,
          "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 12, 0.6, 16, 0.15],
        },
        /* Luz rasante desde el noroeste, no cenital: con el sol de frente todas
           las caras reciben lo mismo y los prismas se ven planos. */
        light: { anchor: "map", position: [1.5, 300, 55], intensity: 0.4 },
      },
      center: CENTRO,
      zoom: ZOOM_INICIAL,
      pitch: 62,
      bearing: -20,
      maxPitch: 80,
      maxBounds: [
        [LIMITES[0] - 0.08, LIMITES[1] - 0.08],
        [LIMITES[2] + 0.08, LIMITES[3] + 0.08],
      ],
      // en v5 el antialias dejó de ser opción de primer nivel y va acá dentro;
      // sin él las aristas de las extrusiones quedan dentadas
      canvasContextAttributes: { antialias: true },
      attributionControl: { compact: true },
    });
    mapa.current = m;

    // asa de depuración: en desarrollo el mapa vive dentro del módulo y no hay
    // forma de inspeccionarlo desde la consola sin esto
    if (process.env.NODE_ENV !== "production") {
      (window as unknown as { __mapa3d?: maplibregl.Map }).__mapa3d = m;
    }

    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-right");
    m.on("load", () => {
      m.addImage("fachada", texturaFachada());
      cargado.current = true;
      setListo(true);
    });

    /* Los errores después de que el mapa cargó NO son fatales y no deben tapar
       la vista. El caso que lo dejó en evidencia: al arrastrar el mapa MapLibre
       aborta las peticiones de las teselas que dejaron de hacer falta, y una
       petición abortada llega acá como "Failed to fetch". Es el funcionamiento
       normal del teselado, no una falla — pero la primera versión mostraba la
       pantalla de error y te dejaba sin mapa apenas movías la cámara. También
       son normales los 404 de teselas fuera del borde de la Ciudad.
       Solo se considera fatal lo que rompe antes de cargar: ahí sí no hay nada
       que mostrar y conviene decir por qué. */
    m.on("error", (e) => {
      const msg = (e?.error as Error | undefined)?.message ?? "";
      if (cargado.current) { console.warn("[3D] error no fatal:", msg); return; }
      if (msg && !/40[34]|Failed to fetch|abort/i.test(msg)) setError(msg);
    });

    // clic sobre un edificio: se destaca en azul y se rotula, como la
    // referencia. Se copia la geometría a una fuente aparte en vez de usar
    // feature-state porque las teselas no traen id estable por edificio.
    // se registra en las dos capas de edificios: cuál está activa depende del
    // zoom, y desde afuera eso no se nota ni tiene por qué notarse
    for (const capaEdificio of ["edificios", "edificios-hitos"]) {
      m.on("click", capaEdificio, (e) => {
        const f = e.features?.[0];
        if (!f) return;
        m.getSource<maplibregl.GeoJSONSource>("destacado")?.setData({
          type: "FeatureCollection",
          features: [{ type: "Feature", properties: { altura: f.properties.altura },
                       geometry: f.geometry }],
        } as FeatureCollection);
        setSel({ altura: Number(f.properties.altura), lngLat: e.lngLat });
      });
      m.on("mouseenter", capaEdificio, () => { m.getCanvas().style.cursor = "pointer"; });
      m.on("mouseleave", capaEdificio, () => { m.getCanvas().style.cursor = ""; });
    }

    return () => { m.remove(); mapa.current = null; };
  }, []);

  /* --- suelo: oscuro o foto aérea --- */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo) return;
    const sat = base === "satelital";
    m.setLayoutProperty("satelital-raster", "visibility", sat ? "visible" : "none");
    /* Con la foto puesta, el agua y el verde dibujados se apagan: la imagen ya
       trae el río y los parques de verdad, y superponerle los polígonos los
       ensucia con un borde que no coincide. Las calles se dejan pero tenues,
       porque sobre la foto sirven de referencia sin taparla. */
    for (const capa of ["agua-fill", "verde-fill"]) {
      m.setLayoutProperty(capa, "visibility", sat ? "none" : "visible");
    }
    // pares (opacidad sobre la foto, opacidad en el modo oscuro); la segunda
    // repite el valor del estilo para no pisarlo con otra cosa al volver
    for (const [capa, sobreFoto, enOscuro] of [
      ["calles-menores", 0.3, 1], ["calles-secundarias", 0.35, 1],
      ["avenidas", 0.45, 1], ["autopistas", 0.7, 0.75],
    ] as const) {
      m.setPaintProperty(capa, "line-opacity", sat ? sobreFoto : enOscuro);
    }
  }, [listo, base]);

  /* --- fachadas lisas o con ventanas --- */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo) return;
    /* Con patrón, MapLibre ignora `fill-extrusion-color`: se pierde el gris que
       aclara con la altura y todos los edificios quedan iguales. Es el precio
       de las ventanas, y por eso esto es un interruptor y no el modo único. */
    for (const capa of ["edificios", "edificios-hitos"]) {
      m.setPaintProperty(capa, "fill-extrusion-pattern", fachadas ? "fachada" : undefined);
    }
  }, [listo, fachadas]);

  /* --- capa de riesgo (piso) --- */
  const cortes = useMemo(() => {
    if (!datos) return [];
    const v = datos.hex.features.map((f) => Number(f.properties[`riesgo_${turno}`]));
    return cortesPorCuantil(v);
  }, [datos, turno]);

  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo || !datos) return;
    const fuente = m.getSource<maplibregl.GeoJSONSource>("riesgo");
    if (!fuente) return;

    if (capa !== "riesgo") { fuente.setData(vacio); return; }
    fuente.setData({
      type: "FeatureCollection",
      features: datos.hex.features.map((f) => {
        const v = Number(f.properties[`riesgo_${turno}`]);
        let clase = 0;
        while (clase < cortes.length && v > cortes[clase]) clase++;
        return { ...f, properties: { ...f.properties, _color: PALETA_RIESGO[clase] } };
      }),
    } as FeatureCollection);
  }, [listo, datos, capa, turno, cortes]);

  /* --- capas operativas --- */
  useEffect(() => {
    const m = mapa.current;
    if (!m || !listo || !datos) return;
    const puntos = m.getSource<maplibregl.GeoJSONSource>("puntos");
    const cob = m.getSource<maplibregl.GeoJSONSource>("coberturas");
    if (!puntos || !cob) return;

    const fs: Feature[] = [];
    const circulos: Feature<Polygon>[] = [];

    if (capa === "camaras") {
      datos.camaras.features.forEach((f) => {
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        fs.push({ type: "Feature", properties: { _clase: "existente", _color: "#7f8a99" },
                  geometry: { type: "Point", coordinates: [lon, lat] } });
      });
      // Sin círculo de cobertura: el Módulo B cubre tramos de la red vial, no un
      // radio. Inventarle un radio sería dibujar un parámetro que no existe.
      datos.moduloB.slice(0, 30).forEach((p) => {
        fs.push({ type: "Feature",
                  properties: { _clase: "propuesto", _color: "#4f8ef7",
                                _tip: `Cámara propuesta #${p.ranking} · ${p.tramos_cubiertos} tramos` },
                  geometry: { type: "Point", coordinates: [p.lon, p.lat] } });
      });
    }

    if (capa === "patrullas") {
      datos.comisarias.features.forEach((f) => {
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        fs.push({ type: "Feature", properties: { _clase: "existente", _color: "#7f8a99" },
                  geometry: { type: "Point", coordinates: [lon, lat] } });
      });
      datos.moduloA.forEach((p) => {
        fs.push({ type: "Feature", properties: { _clase: "propuesto", _color: "#4f8ef7" },
                  geometry: { type: "Point", coordinates: [p.lon, p.lat] } });
        circulos.push(circulo(p.lon, p.lat, RADIO_PATRULLA_M));
      });
    }

    puntos.setData({ type: "FeatureCollection", features: fs } as FeatureCollection);
    cob.setData({ type: "FeatureCollection", features: circulos } as FeatureCollection);
  }, [listo, datos, capa]);

  const leyenda =
    capa === "riesgo" ? ETIQUETAS_CLASE.map((t, i) => ({ t, c: PALETA_RIESGO[i] }))
    : capa === "camaras" ? [{ t: "Existente (224)", c: "#7f8a99" }, { t: "Propuesta (30)", c: "#4f8ef7" }]
    : capa === "patrullas" ? [{ t: "Comisaría actual", c: "#7f8a99" },
                              { t: `Puesto propuesto · radio ${RADIO_PATRULLA_M} m`, c: "#4f8ef7" }]
    : [];

  return (
    <div className="relative h-full w-full bg-[#07080a]">
      {/* El posicionamiento va en estilo en línea y no en clases de Tailwind a
          propósito: MapLibre le agrega la clase `maplibregl-map` a este mismo
          div, y su hoja de estilos declara `.maplibregl-map { position: relative }`.
          Next inyecta ese CSS después del de Tailwind, así que con la misma
          especificidad gana el de MapLibre y pisa a `absolute`. El div queda
          `relative` sin altura propia, con todos sus hijos absolutos, y colapsa
          a 0 px: el mapa renderiza bien pero adentro de una caja invisible.
          El estilo en línea no lo puede pisar ninguna hoja. */}
      <div ref={contenedor} style={{ position: "absolute", inset: 0 }} />

      {/* panel */}
      <div className="absolute left-3 top-3 z-10 w-64 rounded border border-white/10
                      bg-black/70 p-3 text-xs text-slate-200 backdrop-blur">
        <div className="mb-2 font-semibold tracking-wide text-slate-100">CABA en 3D</div>

        <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Suelo</div>
        <div className="mb-3 grid grid-cols-2 gap-1">
          {([["oscura", "Oscuro"], ["satelital", "Foto aérea"]] as const).map(([k, t]) => (
            <button key={k} onClick={() => setBase(k)}
              className={`rounded px-2 py-1 text-left transition ${
                base === k ? "bg-blue-600 text-white" : "bg-white/5 hover:bg-white/10"}`}>
              {t}
            </button>
          ))}
        </div>

        <label className="mb-3 flex cursor-pointer items-center gap-2 text-slate-300">
          <input type="checkbox" checked={fachadas}
            onChange={(e) => setFachadas(e.target.checked)} className="accent-blue-600" />
          Ventanas en las fachadas
        </label>

        <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Capa</div>
        <div className="mb-3 grid grid-cols-2 gap-1">
          {CAPAS.map((c) => (
            <button key={c.key} onClick={() => setCapa(c.key)}
              className={`rounded px-2 py-1 text-left transition ${
                capa === c.key ? "bg-blue-600 text-white" : "bg-white/5 hover:bg-white/10"}`}>
              {c.label}
            </button>
          ))}
        </div>

        {capa === "riesgo" && (
          <>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-slate-400">Turno</div>
            <div className="mb-3 grid grid-cols-2 gap-1">
              {TURNOS.map((t) => (
                <button key={t.key} onClick={() => setTurno(t.key)}
                  className={`rounded px-2 py-1 text-left transition ${
                    turno === t.key ? "bg-blue-600 text-white" : "bg-white/5 hover:bg-white/10"}`}>
                  {t.label}
                </button>
              ))}
            </div>
          </>
        )}

        {leyenda.length > 0 && (
          <div className="space-y-1 border-t border-white/10 pt-2">
            {leyenda.map((l) => (
              <div key={l.t} className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: l.c }} />
                <span className="text-slate-300">{l.t}</span>
              </div>
            ))}
          </div>
        )}

        <p className="mt-3 border-t border-white/10 pt-2 text-[10px] leading-snug text-slate-400">
          Volumetría: Tejido Urbano de la Ciudad (fotogrametría, datos hasta 2021).
          Alturas en múltiplos de 2,8 m — sirven para la silueta, no como cota.
        </p>
      </div>

      {/* rótulo del edificio elegido */}
      {sel && (
        <div className="absolute right-3 top-3 z-10 rounded border border-blue-500/40
                        bg-black/75 px-3 py-2 text-xs text-slate-200 backdrop-blur">
          <div className="text-[10px] uppercase tracking-wider text-blue-400">Edificio</div>
          <div className="text-lg font-semibold tabular-nums text-white">
            {sel.altura.toFixed(1)} m
          </div>
          <div className="text-[10px] text-slate-400">
            ≈ {Math.max(1, Math.round(sel.altura / 2.8))} pisos ·{" "}
            {sel.lngLat.lat.toFixed(5)}, {sel.lngLat.lng.toFixed(5)}
          </div>
          <button onClick={() => {
              setSel(null);
              mapa.current?.getSource<maplibregl.GeoJSONSource>("destacado")?.setData(vacio);
            }}
            className="mt-1 text-[10px] text-slate-400 underline hover:text-slate-200">
            quitar
          </button>
        </div>
      )}

      {!listo && !error && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#07080a] px-6 text-center">
          {oculto ? (
            <div className="max-w-sm">
              <p className="text-xs text-slate-300">Volvé a esta pestaña para dibujar la ciudad.</p>
              <p className="mt-1 text-[11px] leading-snug text-slate-500">
                El navegador congela el dibujado 3D en las pestañas de segundo plano,
                así que la vista arranca recién cuando está al frente.
              </p>
            </div>
          ) : (
            <span className="text-xs text-slate-400">Cargando la ciudad…</span>
          )}
        </div>
      )}
      {error && (
        <div className="absolute inset-0 z-20 grid place-items-center bg-[#07080a] p-6">
          <div className="max-w-md text-center text-xs text-red-300">
            <p className="mb-2 font-semibold">No se pudo cargar la vista 3D</p>
            <p className="text-slate-400">{error}</p>
            <p className="mt-2 text-slate-500">
              Si faltan las teselas, generalas con
              <code className="mx-1 rounded bg-white/10 px-1">
                python pipeline/ingest_tejido_urbano.py
              </code>
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
