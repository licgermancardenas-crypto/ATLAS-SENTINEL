"use client";

import { useEffect, useState } from "react";
import type { FeatureCollection } from "geojson";
import { TURNOS, Turno } from "@/lib/types";
import { cargarDatosDashboard, moduloAaGeojson, moduloBaGeojson, type DatosDashboard } from "@/lib/data";
import { cargarMapaBase, type MapaBase } from "@/lib/mapa";
import MapaSVG from "./MapaSVG";
import ModulePanel from "./ModulePanel";
import MetricsPanel from "./MetricsPanel";
import LimitsPanel from "./LimitsPanel";
import { RISK_RAMP } from "@/lib/color";

type Tab = "capas" | "metricas" | "limites";

export default function Dashboard() {
  const [datos, setDatos] = useState<DatosDashboard | null>(null);
  const [mapa, setMapa] = useState<MapaBase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [turno, setTurno] = useState<Turno>("tarde");
  const [tab, setTab] = useState<Tab>("capas");
  const [toggles, setToggles] = useState({
    moduloA: true,
    moduloB: false,
    comisarias: false,
    camaras: false,
  });

  useEffect(() => {
    cargarDatosDashboard()
      .then(setDatos)
      .catch((e) => setError(String(e)));
    cargarMapaBase()
      .then(setMapa)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div className="p-6 text-status-critical text-sm">Error cargando datos: {error}</div>;
  }
  if (!datos || !mapa) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-secondary text-sm">
        Cargando SIGE-BA…
      </div>
    );
  }

  const moduloAGeojson: FeatureCollection = moduloAaGeojson(datos.moduloA);
  const moduloBGeojson: FeatureCollection = moduloBaGeojson(datos.moduloB);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <header className="flex items-center justify-between px-5 py-3 border-b border-border bg-surface-1">
        <div>
          <h1 className="text-base font-semibold">SIGE-BA</h1>
          <p className="text-xs text-text-secondary">Riesgo de seguridad urbana — CABA</p>
        </div>
        <div className="flex gap-1 bg-surface-2 rounded-lg p-1">
          {TURNOS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTurno(t.key)}
              className={`px-3 py-1.5 text-sm rounded-md cursor-pointer transition-colors duration-150 ${
                turno === t.key
                  ? "bg-[var(--risk-500)] text-white"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        <div className="flex-1 relative">
          <MapaSVG
            turno={turno}
            base={mapa}
            capas={[
              { id: "comisarias", datos: datos.comisarias, visible: toggles.comisarias,
                color: "#ffffff", r: 3.5, nombre: "Comisaría" },
              { id: "camaras", datos: datos.camaras, visible: toggles.camaras,
                color: "#e66767", r: 3, nombre: "Cámara" },
              { id: "moduloB", datos: moduloBGeojson, visible: toggles.moduloB,
                color: "#0ca30c", r: 5, nombre: "Zona prioritaria" },
              { id: "moduloA", datos: moduloAGeojson, visible: toggles.moduloA,
                color: "#d97706", r: 5, nombre: "Patrulla propuesta" },
            ]}
          />
          <RiskLegend />
        </div>

        <aside className="w-80 shrink-0 border-l border-border bg-surface-1 flex flex-col min-h-0">
          <div className="flex border-b border-border">
            <TabButton active={tab === "capas"} onClick={() => setTab("capas")}>Capas</TabButton>
            <TabButton active={tab === "metricas"} onClick={() => setTab("metricas")}>Métricas</TabButton>
            <TabButton active={tab === "limites"} onClick={() => setTab("limites")}>Límites</TabButton>
          </div>
          <div className="flex-1 overflow-y-auto p-4">
            {tab === "limites" ? (
              <LimitsPanel />
            ) : tab === "capas" ? (
              <ModulePanel
                moduloC={datos.moduloC}
                toggles={[
                  { key: "moduloA", label: "Módulo A — patrullas propuestas", color: "#d97706", checked: toggles.moduloA },
                  { key: "moduloB", label: "Módulo B — zonas prioritarias", color: "#0ca30c", checked: toggles.moduloB },
                  { key: "comisarias", label: "Comisarías reales", color: "#ffffff", checked: toggles.comisarias },
                  { key: "camaras", label: "Cámaras reales", color: "#e66767", checked: toggles.camaras },
                ]}
                onToggle={(key) => setToggles((s) => ({ ...s, [key]: !s[key as keyof typeof s] }))}
              />
            ) : (
              <MetricsPanel metricas={datos.metricas} />
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 px-3 py-2.5 text-xs font-medium cursor-pointer transition-colors duration-150 border-b-2 ${
        active ? "border-[var(--risk-400)] text-text-primary" : "border-transparent text-text-secondary hover:text-text-primary"
      }`}
    >
      {children}
    </button>
  );
}

function RiskLegend() {
  return (
    <div className="absolute bottom-4 left-4 bg-surface-2/95 backdrop-blur border border-border rounded-lg px-3 py-2 text-xs">
      <div className="text-text-secondary mb-1.5">Riesgo relativo (por cuantil)</div>
      <div className="flex items-center gap-0.5">
        {RISK_RAMP.map((c) => (
          <span key={c} className="w-6 h-3 first:rounded-l last:rounded-r" style={{ background: c }} />
        ))}
      </div>
      <div className="flex justify-between text-text-secondary mt-0.5">
        <span>bajo</span>
        <span>alto</span>
      </div>
    </div>
  );
}
