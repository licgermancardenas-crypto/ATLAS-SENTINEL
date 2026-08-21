"use client";

import { useEffect, useRef } from "react";
import L from "leaflet";
import type { Feature } from "geojson";
import type {
  BarrioProps, BarriosGeoJSON, Capa, ComunasGeoJSON, DatosDashboard, DemoComuna,
  Superficie, TipoDelito, Turno,
} from "@/lib/types";
import {
  claveDelitos, claveRiesgo, esDemografica, riesgoEsDelTipo, superficieInfo, tipoInfo,
} from "@/lib/types";
import { claseDe, cortesPorCuantil, leerToken, paletaEdad, paletaRiesgo } from "@/lib/escala";
import { num, num1, num2, num3 } from "@/lib/formato";

/* Se usa Leaflet directo y no react-leaflet: el mapa se repinta ante cambios de
   filtro decenas de veces, y manejar las capas a mano evita reconstruir el
   árbol de React en cada cambio. También esquiva el problema conocido de
   react-leaflet con StrictMode montando dos veces.

   Y se usa Leaflet y no MapLibre a propósito: MapLibre renderiza por WebGL, y
   en esta máquina el proceso GPU de Chrome venía crasheando (0xC0000005) con
   querySourceFeatures devolviendo 0 features incluso en un repro mínimo.
   Leaflet dibuja en Canvas/DOM y no toca WebGL. */

const CENTRO: L.LatLngExpression = [-34.6135, -58.4400];
const LIMITES: L.LatLngBoundsLiteral = [[-34.706, -58.532], [-34.526, -58.335]];

// CARTO sirve dos versiones del mismo basemap gris; se elige por tema para que
// el mapa no quede blanco dentro de una interfaz oscura.
const TILES = {
  light: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
};
const ATRIB =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>';

interface Props {
  datos: DatosDashboard;
  turno: Turno;
  capa: Capa;
  superficie: Superficie;
  tipo: TipoDelito;
  comuna: number | null;
  barrioActivo: string | null;
  kPatrullas: number;
  tema: "light" | "dark";
  onBarrio: (nombre: string | null) => void;
}

export default function Mapa({
  datos, turno, capa, superficie, tipo, comuna, barrioActivo, kPatrullas, tema, onBarrio,
}: Props) {
  const nodo = useRef<HTMLDivElement>(null);
  const mapa = useRef<L.Map | null>(null);
  const capaBase = useRef<L.TileLayer | null>(null);
  const capaBarrios = useRef<L.GeoJSON | null>(null);
  const capaComunas = useRef<L.GeoJSON | null>(null);
  const capaPuntos = useRef<L.LayerGroup | null>(null);
  // El callback vive en un ref para que los handlers que Leaflet ya tiene
  // enganchados llamen siempre a la versión actual, sin tener que reconstruir la
  // capa entera cada vez que el padre re-renderiza.
  const onBarrioRef = useRef(onBarrio);
  useEffect(() => { onBarrioRef.current = onBarrio; }, [onBarrio]);

  /* --- creación, una sola vez --- */
  useEffect(() => {
    if (!nodo.current || mapa.current) return;
    const m = L.map(nodo.current, {
      center: CENTRO,
      zoom: 12,
      minZoom: 10,
      maxZoom: 17,
      // Holgado a propósito. Con un maxBounds ajustado, Leaflet directamente no
      // pide los tiles de afuera y el mapa queda con un marco gris plano
      // alrededor de la ciudad, que se lee como un error de carga. Con margen,
      // el conurbano se dibuja normal y la Ciudad aparece recortada sobre su
      // entorno real, que es lo que hace que parezca un mapa y no un diagrama.
      maxBounds: L.latLngBounds(LIMITES).pad(1.2),
      zoomControl: true,
      attributionControl: true,
      preferCanvas: true,
      // Sin esto Leaflet solo usa zooms enteros: fitBounds calcula ~12,6, lo
      // redondea a 12 y la Ciudad queda ocupando un cuarto del lienzo con el
      // conurbano de relleno. Con pasos de 1/4 el encuadre queda ajustado.
      zoomSnap: 0.25,
      zoomDelta: 0.5,
      // El mapa vive dentro de un tablero que scrollea. Con la rueda activa por
      // defecto, bajar la página con el cursor encima hace zoom en vez de
      // scrollear, y uno termina a nivel de calle sin haberlo pedido. Se activa
      // recién cuando alguien hace clic en el mapa, que es cuando declaró que
      // quiere manejarlo, y se apaga al salir. Los botones +/− siempre andan.
      scrollWheelZoom: false,
    });
    m.on("click", () => m.scrollWheelZoom.enable());
    m.on("mouseout", () => m.scrollWheelZoom.disable());
    L.control.scale({ imperial: false, position: "bottomleft" }).addTo(m);
    capaPuntos.current = L.layerGroup().addTo(m);
    mapa.current = m;
    // El encuadre inicial NO puede hacerse acá: cuando corre este efecto el
    // contenedor todavía mide 0 de alto (el grid no resolvió), y fitBounds
    // sobre 0px calcula el zoom mínimo — el mapa termina mostrando media
    // provincia. Se espera al primer resize con alto real y ahí se ajusta.
    let encuadrado = false;
    const ro = new ResizeObserver(([entrada]) => {
      const alto = entrada.contentRect.height;
      if (alto < 40) return;
      m.invalidateSize();
      if (!encuadrado) { m.fitBounds(LIMITES, { padding: [6, 6] }); encuadrado = true; }
    });
    ro.observe(nodo.current);
    return () => { ro.disconnect(); m.remove(); mapa.current = null; };
  }, []);

  /* --- basemap según tema --- */
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;
    capaBase.current?.remove();
    capaBase.current = L.tileLayer(TILES[tema], {
      attribution: ATRIB, subdomains: "abcd", maxZoom: 19, detectRetina: true,
    }).addTo(m);
    capaBase.current.bringToBack();
  }, [tema]);

  /* --- coropleta: riesgo por barrio, o demografía por comuna ---
   *
   *  Las dos superficies se dibujan en el mismo efecto porque son excluyentes
   *  y comparten limpieza: quedarse con las dos capas montadas deja el mapa
   *  pintado dos veces, con la de abajo asomando por los bordes simplificados.
   *
   *  Y son geometrías distintas a propósito. La edad solo existe por comuna;
   *  pintando los 48 barrios con el valor de su comuna, el mapa mostraría 48
   *  formas donde hay 15 datos e invitaría a leer una diferencia entre Palermo
   *  y Colegiales que en el dato no está. */
  useEffect(() => {
    const m = mapa.current;
    if (!m) return;

    capaBarrios.current?.remove();
    capaBarrios.current = null;
    capaComunas.current?.remove();
    capaComunas.current = null;

    const lineaBase = leerToken("--border-strong", "#999");
    const inactivo = leerToken("--risk-nulo", "#e2e8f0");
    const info = superficieInfo(superficie);

    if (esDemografica(superficie)) {
      const campo = info.campo!;
      const valores = datos.comunasGeo.features.map((f) => f.properties[campo]);
      const cortes = cortesPorCuantil(valores);
      const paleta = paletaEdad();

      const estilo = (f?: Feature): L.PathOptions => {
        const p = (f?.properties ?? {}) as DemoComuna;
        const fuera = comuna !== null && p.comuna !== comuna;
        return {
          fillColor: fuera ? inactivo : paleta[claseDe(p[campo], cortes)],
          fillOpacity: fuera ? 0.25 : comuna === p.comuna ? 0.95 : 0.8,
          color: comuna === p.comuna ? leerToken("--brand", "#1e40af") : lineaBase,
          weight: comuna === p.comuna ? 2.5 : 0.9,
          opacity: fuera ? 0.4 : 1,
        };
      };

      capaComunas.current = L.geoJSON(datos.comunasGeo as ComunasGeoJSON, {
        style: estilo,
        onEachFeature: (f, layer) => {
          const p = f.properties as DemoComuna;
          layer.bindTooltip(
            `<strong>Comuna ${p.comuna}</strong><br/>` +
              `<span style="color:var(--text-secondary)">Censo 2022 · ${num(p.poblacion_2022)} hab.</span><br/>` +
              `0 a 14: <strong class="tabular">${num1(p.pct_0_14)}%</strong><br/>` +
              `15 a 64: <strong class="tabular">${num1(p.pct_15_64)}%</strong><br/>` +
              `65 y más: <strong class="tabular">${num1(p.pct_65)}%</strong><br/>` +
              `<span style="color:var(--text-secondary)">Envejecimiento ${num(p.envejecimiento)}</span>`,
            { className: "sige-tip", sticky: true, direction: "top" },
          );
          layer.on({
            mouseover: (e) => (e.target as L.Path).setStyle({ weight: 2, fillOpacity: 0.95 }),
            mouseout: (e) => (e.target as L.Path).setStyle(estilo(f)),
          });
        },
      }).addTo(m);
      capaComunas.current.bringToBack();
      capaBase.current?.bringToBack();
      return;
    }

    const clave = claveRiesgo(turno, tipo);
    const claveD = claveDelitos(tipo);
    const valores = datos.barrios.features.map((f) => f.properties[clave] as number);
    const cortes = cortesPorCuantil(valores);
    const paleta = paletaRiesgo();

    const estilo = (f?: Feature): L.PathOptions => {
      const p = (f?.properties ?? {}) as BarrioProps;
      const fuera = comuna !== null && p.comuna !== comuna;
      const activo = barrioActivo === p.nombre;
      return {
        fillColor: fuera ? inactivo : paleta[claseDe(p[clave] as number, cortes)],
        fillOpacity: fuera ? 0.25 : activo ? 0.95 : 0.78,
        color: activo ? leerToken("--brand", "#1e40af") : lineaBase,
        weight: activo ? 2.5 : 0.7,
        opacity: fuera ? 0.4 : 1,
      };
    };

    capaBarrios.current = L.geoJSON(datos.barrios as BarriosGeoJSON, {
      style: estilo,
      onEachFeature: (f, layer) => {
        const p = f.properties as BarrioProps;
        // el tooltip nombra la superficie que está dibujando, no solo el valor:
        // con el filtro en Vialidad el número es el agregado y hay que decirlo
        const etiquetaRiesgo = riesgoEsDelTipo(tipo)
          ? `Riesgo ${tipoInfo(tipo).label.toLowerCase()} ${TURNO_LABEL[turno]}`
          : `Riesgo ${TURNO_LABEL[turno]}${tipo === "todos" ? "" : " (agregado)"}`;
        const etiquetaDelitos =
          tipo === "todos" ? "Delitos 2025" : `${tipoInfo(tipo).label} 2025`;
        layer.bindTooltip(
          `<strong>${p.nombre}</strong><br/>` +
            `<span style="color:var(--text-secondary)">Comuna ${p.comuna ?? "—"} · ${p.n_hex} celdas</span><br/>` +
            `${etiquetaRiesgo}: <strong class="tabular">${num3(p[clave] as number)}</strong><br/>` +
            `${etiquetaDelitos}: <strong class="tabular">${num(p[claveD] as number)}</strong><br/>` +
            `<span style="color:var(--text-secondary)">${num(p.poblacion as number)} hab.</span>`,
          { className: "sige-tip", sticky: true, direction: "top" },
        );
        layer.on({
          click: () => onBarrioRef.current(barrioActivo === p.nombre ? null : p.nombre),
          mouseover: (e) => (e.target as L.Path).setStyle({ weight: 2, fillOpacity: 0.92 }),
          mouseout: (e) => (e.target as L.Path).setStyle(estilo(f)),
        });
      },
    }).addTo(m);
    capaBarrios.current.bringToBack();
    capaBase.current?.bringToBack();
  }, [datos, turno, tipo, comuna, barrioActivo, superficie]);

  /* --- capa operativa --- */
  useEffect(() => {
    const g = capaPuntos.current;
    if (!g) return;
    g.clearLayers();

    const marcador = (lat: number, lon: number, color: string, r: number, tip: string, relleno = true) =>
      L.circleMarker([lat, lon], {
        radius: r,
        color: relleno ? leerToken("--surface-2", "#fff") : color,
        weight: relleno ? 1.5 : 2,
        fillColor: color,
        fillOpacity: relleno ? 0.95 : 0.25,
      }).bindTooltip(tip, { className: "sige-tip", direction: "top" });

    const existente = leerToken("--pt-existente", "#64748b");
    const propuesto = leerToken("--pt-propuesto", "#1e40af");
    const alerta = leerToken("--pt-alerta", "#b91c1c");

    if (capa === "patrullas") {
      datos.comisarias.features.forEach((f) => {
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        g.addLayer(marcador(lat, lon, existente, 4,
          `<strong>Comisaría actual</strong><br/>${f.properties?.nombre ?? ""}`));
      });
      datos.moduloA.slice(0, kPatrullas).forEach((p, i) => {
        g.addLayer(marcador(p.lat, p.lon, propuesto, 6,
          `<strong>Patrulla propuesta #${i + 1}</strong><br/>` +
          `<span style="color:var(--text-secondary)">${p.tipo === "comisaría existente"
            ? "Reutiliza una comisaría que ya existe" : "Puesto nuevo"}</span><br/>Comuna ${p.comuna}`));
      });
    }

    if (capa === "camaras") {
      datos.camaras.features.forEach((f) => {
        const [lon, lat] = (f.geometry as GeoJSON.Point).coordinates;
        g.addLayer(marcador(lat, lon, existente, 3, "<strong>Cámara existente</strong><br/>Fiscalización vehicular"));
      });
      datos.moduloB.slice(0, 30).forEach((p) => {
        g.addLayer(marcador(p.lat, p.lon, propuesto, 6,
          `<strong>Cámara propuesta #${p.ranking}</strong><br/>` +
          `Cubre <strong class="tabular">${p.tramos_cubiertos}</strong> tramos<br/>` +
          `Ganancia <strong class="tabular">${num2(p.ganancia_marginal)}</strong>`));
      });
    }

    if (capa === "controles") {
      datos.moduloC.forEach((p) => {
        // el tamaño codifica el puesto: el 1º es el círculo más grande
        const r = 12 - (p.ranking - 1) * 0.8;
        g.addLayer(marcador(p.lat, p.lon, alerta, Math.max(5, r),
          `<strong>#${p.ranking} · ${p.nombre}</strong><br/>` +
          `<span style="color:var(--text-secondary)">${p.autopista}</span><br/>` +
          `Siniestros por celda: <strong class="tabular">${num(p.accidentalidad_por_hex)}</strong><br/>` +
          `Riesgo del corredor: <strong class="tabular">${num2(p.riesgo_delictivo_corredor)}</strong>`));
      });
    }
  }, [datos, capa, kPatrullas]);

  /* --- encuadre al filtrar por comuna --- */
  useEffect(() => {
    const m = mapa.current;
    // con una superficie demográfica no hay capa de barrios montada: el
    // encuadre sale de la de comunas, que además ya es un polígono por comuna
    const capaB = capaBarrios.current ?? capaComunas.current;
    if (!m || !capaB) return;
    if (comuna === null) { m.flyToBounds(LIMITES, { duration: 0.5 }); return; }
    const seleccion: L.LatLngBounds[] = [];
    capaB.eachLayer((l) => {
      const f = (l as L.GeoJSON).feature;
      const p = (f && "properties" in f ? f.properties : undefined) as
        { comuna?: number | null } | undefined;
      if (p?.comuna === comuna) seleccion.push((l as L.Polygon).getBounds());
    });
    if (seleccion.length) {
      const b = L.latLngBounds(seleccion[0].getSouthWest(), seleccion[0].getNorthEast());
      seleccion.slice(1).forEach((x) => b.extend(x));
      m.flyToBounds(b.pad(0.15), { duration: 0.5 });
    }
    // sin `superficie` en las dependencias a propósito: el efecto lee la capa
    // vigente al correr, y volver a encuadrar al cambiar de superficie le
    // pisaría el zoom a quien ya se había acercado a mirar algo
  }, [comuna]);

  return <div ref={nodo} className="h-full w-full" role="application"
              aria-label="Mapa de riesgo por barrio de la Ciudad de Buenos Aires" />;
}

const TURNO_LABEL: Record<Turno, string> = {
  manana: "mañana", tarde: "tarde", noche: "noche", madrugada: "madrugada",
};
