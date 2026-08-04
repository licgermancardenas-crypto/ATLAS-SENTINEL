import type { Metricas } from "@/lib/types";
import StatCard from "./StatCard";
import CalibracionChart from "./CalibracionChart";
import EvolucionChart from "./EvolucionChart";

export default function MetricsPanel({ metricas }: { metricas: Metricas }) {
  const { v1, recall_20: r20v1 } = { v1: metricas.v1_vs_v2.v1, recall_20: metricas.v1_vs_v2.v1.recall_20 };
  const baseline = metricas.v1_vs_v2.baseline_naive;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h3 className="text-sm font-semibold mb-2">Modelo núcleo (test 2025)</h3>
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="MAE" value={v1.mae.toFixed(3)} delta={{ label: `baseline ${baseline.mae.toFixed(3)}`, positivo: v1.mae < baseline.mae }} />
          <StatCard label="Recall@20% área" value={`${(r20v1 * 100).toFixed(1)}%`} delta={{ label: `baseline ${(baseline.recall_20 * 100).toFixed(1)}%`, positivo: r20v1 > baseline.recall_20 }} />
        </div>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Calibración por decil</h3>
        <p className="text-xs text-text-secondary mb-2">Predicho vs. real — cerca de la diagonal punteada = bien calibrado.</p>
        <CalibracionChart datos={metricas.calibracion} />
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-1">Estabilidad mes a mes</h3>
        <EvolucionChart datos={metricas.evolucion_mensual} />
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2">Módulo A — cobertura vs. presupuesto</h3>
        <div className="grid grid-cols-2 gap-2">
          <StatCard label="Actual (75 comisarías)" value={`${(metricas.modulo_a_cobertura.actual_75_comisarias * 100).toFixed(1)}%`} />
          <StatCard
            label="Optimizado, K=75"
            value={`${(metricas.modulo_a_cobertura.k75 * 100).toFixed(1)}%`}
            delta={{ label: `+${((metricas.modulo_a_cobertura.k75 - metricas.modulo_a_cobertura.actual_75_comisarias) * 100).toFixed(1)}pp mismo presupuesto`, positivo: true }}
          />
        </div>
      </div>
    </div>
  );
}
