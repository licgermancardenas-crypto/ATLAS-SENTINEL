"use client";

import { useMemo, useState } from "react";
import type { FeatureCollection } from "geojson";
import { Turno } from "@/lib/types";
import { RISK_RAMP, quantileBreaks } from "@/lib/color";
import type { MapaBase } from "@/lib/mapa";
import { proyectar } from "@/lib/mapa";

/**
 * Mapa de riesgo dibujado como SVG, sin MapLibre.
 *
 * MapLibre no dibujaba ninguna capa vectorial en este entorno: su worker se
 * instanciaba pero devolvía CERO features para cualquier fuente GeoJSON —
 * reproducido en una página HTML plana, sin bundler, con los 401 hexágonos
 * reales y con un triángulo de tres puntos escrito a mano. Aparte, el proceso
 * GPU de Chrome se caía al compilar sus shaders en esta GPU.
 *
 * El SVG no necesita worker, ni WebGL, ni tiles: esquiva las dos causas. La
 * geometría (silueta real de la ciudad, red vial de OSM, hexágonos) viene
 * pre-proyectada en mapa_base.json — ver src/export/generar_mapa_svg.py.
 */

interface CapaPuntos {
  id: string;
  datos: FeatureCollection | null;
  visible: boolean;
  color: string;
  r: number;
  nombre: string;
}

interface Props {
  turno: Turno;
  base: MapaBase;
  capas: CapaPuntos[];
}

interface Tip {
  x: number;
  y: number;
  titulo: string;
  detalle: string;
}

export default function MapaSVG({ turno, base, capas }: Props) {
  const [tip, setTip] = useState<Tip | null>(null);
  const { w, h } = base.proyeccion;

  // los cortes se recalculan por turno: el riesgo está muy sesgado y una
  // escala fija dejaría casi todo en el mismo color (misma razón que en la
  // versión anterior, ver lib/color.ts)
  const binDe = useMemo(() => {
    const valores = base.hex.map((x) => x[turno]);
    const cortes = quantileBreaks(valores, RISK_RAMP.length);
    return (v: number) => {
      for (let i = 0; i < cortes.length; i++) if (v <= cortes[i]) return i;
      return cortes.length;
    };
  }, [base.hex, turno]);

  const puntos = useMemo(
    () =>
      capas
        .filter((c) => c.visible && c.datos)
        .map((c) => ({
          ...c,
          // todas las capas de puntos son Point; el cast pasa por unknown
          // porque GeometryCollection no tiene `coordinates` y TS lo marca
          pts: c.datos!.features.map((f) => {
            const [lon, lat] = (f.geometry as unknown as { coordinates: [number, number] }).coordinates;
            return { ...proyectar(base.proyeccion, lon, lat), props: f.properties ?? {} };
          }),
        })),
    [capas, base.proyeccion]
  );

  return (
    <div className="relative w-full h-full overflow-hidden bg-[var(--mapa-agua)]">
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full h-full"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={`Mapa de la Ciudad de Buenos Aires: riesgo del turno ${turno} por hexágono, sobre la red vial real.`}
      >
        <rect x="0" y="0" width={w} height={h} className="fill-[var(--mapa-agua)]" />
        <path d={base.tierra} fillRule="evenodd" className="fill-[var(--mapa-tierra)]" />

        <path d={base.vias.menor} className="fill-none stroke-[var(--via-menor)]" strokeWidth={0.5} />
        <path d={base.vias.media} className="fill-none stroke-[var(--via-media)]" strokeWidth={0.9} />

        <g>
          {base.hex.map((hx) => (
            <path
              key={hx.id}
              d={hx.d}
              fill={RISK_RAMP[binDe(hx[turno])]}
              fillOpacity={0.62}
              stroke="none"
              onMouseEnter={() =>
                setTip({
                  x: 0,
                  y: 0,
                  titulo: `${hx.barrio ?? "sin barrio"} · Comuna ${hx.comuna ?? "—"}`,
                  detalle: `Riesgo ${turno}: ${hx[turno].toFixed(3)}`,
                })
              }
              onMouseLeave={() => setTip(null)}
            />
          ))}
        </g>

        {/* avenidas y autopistas por encima del riesgo: sin esto la mancha
            tapa la trama urbana y el mapa deja de leerse como mapa */}
        <path d={base.vias.media} className="fill-none stroke-[var(--via-media)]" strokeWidth={0.9} opacity={0.8} />
        <path d={base.vias.troncal} className="fill-none stroke-[var(--via-troncal)]" strokeWidth={1.8} />
        <path d={base.barrios} fillRule="evenodd" className="fill-none stroke-[var(--barrio-linea)]" strokeWidth={0.8} />

        {puntos.map((c) => (
          <g key={c.id}>
            {c.pts.map((p, i) => (
              <circle
                key={i}
                cx={p.x}
                cy={p.y}
                r={c.r}
                fill={c.color}
                stroke="var(--mapa-tierra)"
                strokeWidth={1.2}
                onMouseEnter={() =>
                  setTip({
                    x: 0,
                    y: 0,
                    titulo: c.nombre,
                    detalle: String(p.props.nombre ?? p.props.hex_id ?? ""),
                  })
                }
                onMouseLeave={() => setTip(null)}
              />
            ))}
          </g>
        ))}
      </svg>

      {tip && (
        <div className="absolute top-3 left-3 bg-surface-2/95 backdrop-blur border border-border rounded-lg px-3 py-2 text-xs pointer-events-none">
          <div className="font-semibold">{tip.titulo}</div>
          <div className="text-text-secondary">{tip.detalle}</div>
        </div>
      )}
    </div>
  );
}
