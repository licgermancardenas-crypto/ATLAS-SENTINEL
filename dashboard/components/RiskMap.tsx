"use client";

import { useEffect, useRef, useState } from "react";
import {
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type GeoJSONSource,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { FeatureCollection } from "geojson";
import { Turno } from "@/lib/types";
import { colorScaleExpression, quantileBreaks } from "@/lib/color";

const CABA_CENTER: [number, number] = [-58.4416, -34.6118];

// Basemap oscuro de CARTO (XYZ raster, sin API key) — coincide con el tema dark.
const BASEMAP_STYLE = {
  version: 8 as const,
  sources: {
    carto: {
      type: "raster" as const,
      tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"],
      tileSize: 256,
      attribution:
        '© <a href="https://carto.com/attributions">CARTO</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
  },
  layers: [{ id: "carto", type: "raster" as const, source: "carto" }],
};

interface Props {
  turno: Turno;
  hexData: FeatureCollection | null;
  showModuloA: boolean;
  showModuloB: boolean;
  showComisarias: boolean;
  showCamaras: boolean;
  moduloAData: FeatureCollection | null;
  moduloBData: FeatureCollection | null;
  comisariasData: FeatureCollection | null;
  camarasData: FeatureCollection | null;
}

export default function RiskMap({
  turno,
  hexData,
  showModuloA,
  showModuloB,
  showComisarias,
  showCamaras,
  moduloAData,
  moduloBData,
  comisariasData,
  camarasData,
}: Props) {
  const contenedorRef = useRef<HTMLDivElement>(null);
  const mapaRef = useRef<MapLibreMap | null>(null);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (!contenedorRef.current || mapaRef.current) return;
    const mapa = new MapLibreMap({
      container: contenedorRef.current,
      style: BASEMAP_STYLE,
      center: CABA_CENTER,
      zoom: 11.3,
      attributionControl: { compact: true },
    });
    mapa.addControl(new NavigationControl({ showCompass: false }), "top-right");
    mapa.on("load", () => setListo(true));
    mapaRef.current = mapa;
    return () => {
      mapa.remove();
      mapaRef.current = null;
    };
  }, []);

  // capa de riesgo por hexágono
  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo || !hexData) return;

    const propiedad = `riesgo_${turno}`;
    const valores = hexData.features.map((f) => (f.properties as Record<string, number>)[propiedad] ?? 0);
    const breaks = quantileBreaks(valores, 7);
    const expresion = colorScaleExpression(propiedad, breaks);

    if (!mapa.getSource("hex")) {
      mapa.addSource("hex", { type: "geojson", data: hexData });
      mapa.addLayer({
        id: "hex-fill",
        type: "fill",
        source: "hex",
        paint: { "fill-color": expresion, "fill-opacity": 0.75 },
      });
      mapa.addLayer({
        id: "hex-outline",
        type: "line",
        source: "hex",
        paint: { "line-color": "#0b0b0b", "line-opacity": 0.15, "line-width": 0.5 },
      });

      const popup = new Popup({ closeButton: false, closeOnMove: true });
      mapa.on("mousemove", "hex-fill", (e) => {
        mapa.getCanvas().style.cursor = "pointer";
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties as Record<string, string | number>;
        popup
          .setLngLat(e.lngLat)
          .setHTML(
            `<div style="font-family:var(--font-fira-sans);font-size:13px">
              <strong>${p.barrio}</strong> · Comuna ${p.comuna}<br/>
              <span style="color:var(--text-secondary)">Riesgo ${turno}: </span><strong>${(p[propiedad] as number).toFixed(3)}</strong>
            </div>`
          )
          .addTo(mapa);
      });
      mapa.on("mouseleave", "hex-fill", () => {
        mapa.getCanvas().style.cursor = "";
        popup.remove();
      });
    } else {
      (mapa.getSource("hex") as GeoJSONSource).setData(hexData);
      mapa.setPaintProperty("hex-fill", "fill-color", expresion);
    }
  }, [listo, hexData, turno]);

  // capas de puntos (módulos + contexto)
  useMarkerLayer(mapaRef, listo, "modulo-a", moduloAData, showModuloA, "#d97706", 6);
  useMarkerLayer(mapaRef, listo, "modulo-b", moduloBData, showModuloB, "#0ca30c", 6);
  useMarkerLayer(mapaRef, listo, "comisarias", comisariasData, showComisarias, "#ffffff", 3.5);
  useMarkerLayer(mapaRef, listo, "camaras", camarasData, showCamaras, "#e66767", 3.5);

  return <div ref={contenedorRef} className="w-full h-full" />;
}

function useMarkerLayer(
  mapaRef: React.RefObject<MapLibreMap | null>,
  listo: boolean,
  id: string,
  data: FeatureCollection | null,
  visible: boolean,
  color: string,
  radius: number
) {
  useEffect(() => {
    const mapa = mapaRef.current;
    if (!mapa || !listo || !data) return;

    if (!mapa.getSource(id)) {
      mapa.addSource(id, { type: "geojson", data });
      mapa.addLayer({
        id: `${id}-circle`,
        type: "circle",
        source: id,
        paint: {
          "circle-radius": radius,
          "circle-color": color,
          "circle-stroke-width": 1.5,
          "circle-stroke-color": "#101012",
        },
        layout: { visibility: visible ? "visible" : "none" },
      });
    } else {
      mapa.setLayoutProperty(`${id}-circle`, "visibility", visible ? "visible" : "none");
    }
  }, [mapaRef, listo, id, data, visible, color, radius]);
}
